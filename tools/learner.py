#!/usr/bin/env python3
"""
The learner's private profile, learner model and per-subject plans. Everything is written
under learner/ (git-ignored, never shared in Phase 1). Standard library only.

    python tools/learner.py onboard --answers '<json>'      # write profile + learner model
    python tools/learner.py plan <subject> [--answers '<json>']   # build or rebuild a plan
    python tools/learner.py progress <subject> <module> <not-started|in-progress|done>
    python tools/learner.py model --set pace=slow --add weak_areas=fractions --remove weak_areas=x
    python tools/learner.py notes <subject> <module> <batch number> [--extra "text"]
    python tools/learner.py add-term "<personal term>"     # name, school, city... (kept private)
    python tools/learner.py show                           # summary for the start of a session

Commands print nothing on success (only `show` prints, for the agent). Failures go to
learner/tutor.log; onboard and plan also explain bad answers on stderr, for the agent.
--answers takes a JSON object, or @path/to/file.json. Answer fields: core/teaching/onboarding.md.
Set TUTOR_ROOT to use another folder as the repo root (tests do this).
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
AGE_BANDS = ["under-13", "13-17", "18-24", "25-34", "35-44", "45-54", "55+"]
STUDENT_BANDS = {"under-13", "13-17"}
LEVELS = ["primary", "middle", "secondary", "college", "postgraduate", "professional", "self-learner"]
JOURNEY_STAGES = ["new", "beginner", "intermediate", "advanced", "revising"]
PACES = ["slow", "steady", "fast"]
STYLES = ["hands-on", "step-by-step", "examples", "analogies", "visual", "theory-first",
          "practice-questions", "discussion"]
STATUSES = ["not-started", "in-progress", "done"]
MAX_ITEMS, MAX_TEXT = 10, 200
# Learner-model fields and their rules. Mirrors TECH_SPEC §5.1 learner_model.
MODEL_LISTS = {
    "goals": "text",
    "preferred_styles": STYLES,
    "strengths": "slug",
    "weak_areas": "slug",
    "what_works": "text",
}
MODEL_VALUES = {"journey_stage": JOURNEY_STAGES, "pace": PACES}
SUBJECT_EXTRA_KEYS = {"pace_weeks", "hours_per_day", "start_date",
                      # school and college subjects (core/teaching/onboarding.md, round 4)
                      "board", "textbook", "edition", "exam_units", "exam_date"}
# Boards are categories, never institution names: a university is just "university"
# (its name goes to learner/private_terms.json).
BOARDS = ["cbse", "cisce", "nios", "ib", "cambridge", "state-board", "university", "other"]
ACADEMIC_LEVELS = {"primary", "middle", "secondary", "college", "postgraduate"}


class TutorError(Exception):
    """A problem the agent should fix and retry (bad answer, unknown subject...)."""


# ---------- paths and files ----------

def learner_dir(root=None):
    return Path(root or ROOT) / "learner"


def subject_dir(subject, root=None):
    return learner_dir(root) / "subjects" / subject


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def today():
    return dt.date.today().isoformat()


def parse_answers(raw):
    if raw is None:
        return None
    text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TutorError(f"--answers is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise TutorError("--answers must be a JSON object")
    return data


# ---------- validation helpers ----------

def check_choice(name, value, allowed):
    if value not in allowed:
        raise TutorError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def check_text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise TutorError(f"{name} must be non-empty text")
    value = " ".join(value.split())
    if len(value) > MAX_TEXT:
        raise TutorError(f"{name} must be at most {MAX_TEXT} characters")
    return value


def check_item(field, value):
    kind = MODEL_LISTS[field]
    if kind == "text":
        return check_text(field, value)
    if kind == "slug":
        if not isinstance(value, str) or not SLUG.match(value):
            raise TutorError(f"{field} entries are topic slugs like 'fractions' or 'locators', got {value!r}")
        return value
    return check_choice(field, value, kind)


def check_list(field, values):
    if not isinstance(values, list):
        raise TutorError(f"{field} must be a list")
    out = []
    for v in values:
        v = check_item(field, v)
        if v not in out:
            out.append(v)
    if len(out) > MAX_ITEMS:
        raise TutorError(f"{field} can hold at most {MAX_ITEMS} entries; drop or merge some")
    return out


def check_hours(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.25 <= value <= 12:
        raise TutorError(f"hours_per_day must be a number from 0.25 to 12, got {value!r}")
    return value


# ---------- onboarding ----------

def mode_for(age_band):
    return "student" if age_band in STUDENT_BANDS else "adult"


def onboard(answers, root=None):
    """Write learner/profile.json and learner/model.json from universal onboarding answers."""
    known = {"name", "age_band", "level", "explain_language", "goals", "preferred_styles",
             "pace", "hours_per_day", "journey_stage"}
    unknown = set(answers) - known
    if unknown:
        raise TutorError(f"unknown onboarding fields: {sorted(unknown)}; allowed: {sorted(known)}")
    if "age_band" not in answers:
        raise TutorError("age_band is required (ask it first)")
    if "level" not in answers:
        raise TutorError("level is required")
    age_band = check_choice("age_band", answers["age_band"], AGE_BANDS)
    language = answers.get("explain_language", "en")
    if not isinstance(language, str) or not LANG.match(language):
        raise TutorError("explain_language must be a BCP-47 tag such as 'en', 'hi' or 'es-MX'")
    name = answers.get("name")
    if name is not None:
        name = check_text("name", name)

    existing = read_json(learner_dir(root) / "profile.json", {})
    profile = {
        "name": name,
        "age_band": age_band,
        "mode": mode_for(age_band),
        "level": check_choice("level", answers["level"], LEVELS),
        "explain_language": language,
        "hours_per_day": check_hours(answers.get("hours_per_day", 1)),
        "sharing": False,
        "created": existing.get("created") or today(),
        "subjects": existing.get("subjects", []),
    }
    model = {
        "goals": check_list("goals", answers.get("goals", [])),
        "journey_stage": check_choice("journey_stage", answers.get("journey_stage", "new"), JOURNEY_STAGES),
        "preferred_styles": check_list("preferred_styles", answers.get("preferred_styles", [])),
        "pace": check_choice("pace", answers.get("pace", "steady"), PACES),
        "strengths": [],
        "weak_areas": [],
        "what_works": [],
        "updated": today(),
    }
    old_model = read_json(learner_dir(root) / "model.json")
    if old_model:  # re-onboarding keeps what was learned about the learner
        for key in ("strengths", "weak_areas", "what_works"):
            model[key] = old_model.get(key, [])
    for key in ("sharing", "sharing_asked", "sharing_changed", "code_shown", "gh_login_asked"):
        if key in existing:
            profile[key] = existing[key]
    if profile["mode"] == "student":
        # a student has no identity: remove one left from an earlier (adult) answer
        if identity_path(root).exists():
            identity_path(root).unlink()
    write_json(learner_dir(root) / "profile.json", profile)
    write_json(learner_dir(root) / "model.json", model)
    if profile["mode"] == "adult":
        try:
            init_identity(root)
        except ImportError as exc:  # pynacl missing: teaching goes on, retried at session start
            tutorlog.log(root or ROOT, "learner", f"identity not created yet: {exc}")
    if name:  # the full name and each part of it, since people often use one part alone
        for term in [name] + [p for p in name.split() if len(p) >= 2]:
            add_private_term(term, root)
    return profile, model


def update_model(sets=(), adds=(), removes=(), root=None):
    path = learner_dir(root) / "model.json"
    model = read_json(path)
    if model is None:
        raise TutorError("no learner/model.json yet; run onboard first")
    for key, value in sets:
        if key in MODEL_VALUES:
            model[key] = check_choice(key, value, MODEL_VALUES[key])
        elif key in MODEL_LISTS:
            model[key] = check_list(key, [v for v in value.split(",") if v] if isinstance(value, str) else value)
        else:
            raise TutorError(f"unknown model field {key!r}")
    for key, value in adds:
        if key not in MODEL_LISTS:
            raise TutorError(f"can only --add to list fields: {sorted(MODEL_LISTS)}")
        value = check_item(key, value)
        items = [v for v in model.get(key, []) if v != value] + [value]
        if len(items) > MAX_ITEMS:
            items = items[-MAX_ITEMS:]  # keep the newest
        model[key] = items
    for key, value in removes:
        if key not in MODEL_LISTS:
            raise TutorError(f"can only --remove from list fields: {sorted(MODEL_LISTS)}")
        model[key] = [v for v in model.get(key, []) if v != value]
    if "weak_areas" in model and "strengths" in model:
        # a topic can't be both; the latest change wins
        changed_strengths = {v for k, v in adds if k == "strengths"}
        changed_weak = {v for k, v in adds if k == "weak_areas"}
        model["weak_areas"] = [w for w in model["weak_areas"] if w not in changed_strengths]
        model["strengths"] = [s for s in model["strengths"] if s not in changed_weak]
    model["updated"] = today()
    write_json(path, model)
    return model


def add_private_term(term, root=None):
    term = " ".join(str(term).split())
    if not term:
        raise TutorError("term is empty")
    path = learner_dir(root) / "private_terms.json"
    data = read_json(path, {"terms": []})
    if term.lower() not in {t.lower() for t in data["terms"]}:
        data["terms"].append(term)
        write_json(path, data)
    return data["terms"]


# ---------- identity, learner code, sharing (TECH_SPEC §4, §9) ----------

ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
LEARNER_ID = re.compile(r"^lrn-[a-hjkmnp-z2-9]{8}$")
CODE_WARNING = ("Keep this private, like a password. It lets you continue on another device "
                "and delete your data.")


def tutor_dir(root=None):
    return Path(root or ROOT) / ".tutor"


def identity_path(root=None):
    return tutor_dir(root) / "identity.json"


def write_private_json(path, data):
    """Write a file only the owner can read (mode 0600)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def init_identity(root=None):
    """Create the adult learner's id and signing key once. Students never get one."""
    profile = read_json(learner_dir(root) / "profile.json")
    if profile is None:
        raise TutorError("no learner/profile.json yet; run onboard first")
    if profile.get("mode") != "adult":
        raise TutorError("student mode has no identity")
    existing = read_json(identity_path(root))
    if existing:
        return existing
    import secrets
    from nacl.signing import SigningKey
    import base64
    identity = {
        "learner_id": "lrn-" + "".join(secrets.choice(ID_ALPHABET) for _ in range(8)),
        "signing_seed_b64": base64.b64encode(bytes(SigningKey.generate())).decode(),
        "created": today(),
    }
    write_private_json(identity_path(root), identity)
    return identity


def learner_code(root=None):
    import base64
    identity = read_json(identity_path(root))
    if not identity:
        raise TutorError("no identity (adults only, created at onboarding)")
    seed = base64.b64decode(identity["signing_seed_b64"])
    return f"{identity['learner_id']}.{base64.b32encode(seed).decode().rstrip('=')}"


def restore_identity(code, root=None):
    """Recreate .tutor/identity.json from a learner code typed on another device."""
    import base64
    code = "".join(str(code).split())
    learner_id, _, secret = code.partition(".")
    if not LEARNER_ID.match(learner_id) or not secret:
        raise TutorError("that doesn't look like a learner code")
    try:
        seed = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    except (ValueError, base64.binascii.Error):
        raise TutorError("that doesn't look like a learner code")
    if len(seed) != 32:
        raise TutorError("that doesn't look like a learner code")
    identity = {"learner_id": learner_id, "signing_seed_b64": base64.b64encode(seed).decode(), "created": today()}
    write_private_json(identity_path(root), identity)
    profile = read_json(learner_dir(root) / "profile.json")
    if profile is not None:
        profile["code_shown"] = True  # they already have it
        write_json(learner_dir(root) / "profile.json", profile)
    return identity


def set_profile_flag(key, value, root=None):
    path = learner_dir(root) / "profile.json"
    profile = read_json(path)
    if profile is None:
        raise TutorError("no learner/profile.json yet; run onboard first")
    profile[key] = value
    write_json(path, profile)
    return profile


SHARING_PACKAGES = {"nacl": "pynacl", "jsonschema": "jsonschema"}  # import name -> package


def missing_packages():
    """Packages sharing needs that aren't importable yet."""
    import importlib.util
    importlib.invalidate_caches()
    return [pkg for mod, pkg in SHARING_PACKAGES.items() if importlib.util.find_spec(mod) is None]


# Exact versions with hashes only: no dependency resolution, nothing unpinned or unhashed.
STRICT_INSTALL_FLAGS = ["--require-hashes", "--no-deps"]


def installer_commands(target, requirements):
    """The commands to try, in order. Every one checks hashes and installs no extra deps."""
    import importlib.util
    import shutil
    args = [*STRICT_INSTALL_FLAGS, "--target", str(target), "-r", str(requirements)]
    if os.environ.get("TUTOR_PIP_COMMAND"):  # tests only: a stand-in installer
        return [json.loads(os.environ["TUTOR_PIP_COMMAND"]) + args]
    runners = []
    if importlib.util.find_spec("pip"):
        runners.append([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--no-input", *args])
    if shutil.which("uv"):
        runners.append(["uv", "pip", "install", "--quiet", "--python", sys.executable, *args])
    return runners


def install_packages(root=None):
    """Install requirements-tutor.txt into .tutor/pylib. Only after the learner said yes to
    installing them (TECH_SPEC §1 exception, owner decision 2026-11-03). Never touches the
    system Python. Raises TutorError if no installer works."""
    import subprocess
    root = Path(root or ROOT)
    target = tutor_dir(root) / "pylib"
    target.mkdir(parents=True, exist_ok=True)
    runners = installer_commands(target, root / "requirements-tutor.txt")
    errors = []
    for command in runners:
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
            continue
        if done.returncode == 0:
            if str(target) not in sys.path:
                sys.path.insert(1, str(target))
            if not missing_packages():
                return target
            errors.append("installed, but the packages still can't be imported")
        else:
            errors.append((done.stderr or done.stdout).strip()[-300:])
    raise TutorError("could not install the sharing packages ("
                     + ("; ".join(errors) if errors else "no pip or uv on this computer") + ")")


def set_sharing(on, root=None):
    """The learner's answer to the consent question (changeable any time). Sharing can't be
    turned on until the packages it needs are installed."""
    if on and missing_packages():
        raise TutorError(f"sharing needs {', '.join(missing_packages())}: ask the learner, in the same "
                         "consent moment, whether you may install them (python tools/learner.py "
                         "install-sharing-packages); if they say no, sharing stays off")
    profile = set_profile_flag("sharing", bool(on), root)
    profile["sharing_asked"] = True
    profile["sharing_changed"] = today()
    write_json(learner_dir(root) / "profile.json", profile)
    return profile


# ---------- subjects and plans ----------

def load_catalog(subject, root=None):
    if not SLUG.match(subject or ""):
        raise TutorError(f"subject id {subject!r} is not a slug")
    path = Path(root or ROOT) / "core" / "subjects" / subject / "catalog.json"
    catalog = read_json(path)
    if catalog is None:
        raise TutorError(f"no catalog for {subject!r}. Write core/subjects/{subject}/catalog.json first "
                         "(core/teaching/subject-catalog.md), add it to core/subjects/index.json, "
                         "and run python tools/validate.py")
    return catalog


def check_subject_answers(catalog, answers):
    questions = {q["id"]: q for q in catalog.get("questions", [])}
    unknown = set(answers) - set(questions) - SUBJECT_EXTRA_KEYS
    if unknown:
        raise TutorError(f"unknown answers for {catalog['subject']}: {sorted(unknown)}; "
                         f"questions are {sorted(questions)}")
    clean = {}
    for qid, q in questions.items():
        if qid not in answers:
            continue
        allowed = [o["value"] for o in q["options"]]
        value = answers[qid]
        if q.get("multi"):
            if not isinstance(value, list):
                raise TutorError(f"{qid} takes a list of answers")
            for v in value:
                check_choice(qid, v, allowed)
            clean[qid] = list(dict.fromkeys(value))
        else:
            clean[qid] = check_choice(qid, value, allowed)
    if "pace_weeks" in answers:
        pw = answers["pace_weeks"]
        if isinstance(pw, bool) or not isinstance(pw, int) or not 0 <= pw <= 520:
            raise TutorError("pace_weeks must be a whole number of weeks (0 = no deadline)")
        clean["pace_weeks"] = pw
    if "hours_per_day" in answers:
        clean["hours_per_day"] = check_hours(answers["hours_per_day"])
    for key in ("start_date", "exam_date"):
        if key in answers:
            try:
                clean[key] = dt.date.fromisoformat(answers[key]).isoformat()
            except (TypeError, ValueError):
                raise TutorError(f"{key} must be YYYY-MM-DD")
    if "board" in answers:
        clean["board"] = check_choice("board", answers["board"], BOARDS)
    for key, limit in (("textbook", 120), ("edition", 40)):
        if key in answers:
            value = answers[key]
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise TutorError(f"{key} must be text of at most {limit} characters")
            clean[key] = " ".join(value.split())
    syllabus = catalog.get("syllabus")
    if syllabus:
        # the plan follows the learner's own book: the catalog must be the one built from it
        for key in ("board", "textbook", "edition"):
            if key in clean and str(syllabus.get(key, "")).lower() != clean[key].lower():
                raise TutorError(f"this catalog follows {key} {syllabus.get(key)!r} but the learner's is "
                                 f"{clean[key]!r}; build a catalog from the learner's own chapter list first "
                                 "(core/teaching/generating-lessons.md)")
    if "exam_units" in answers:
        units = answers["exam_units"]
        module_ids = [m["id"] for m in catalog["modules"]]
        if units == "all":
            clean["exam_units"] = "all"
        elif isinstance(units, list) and units:
            missing = [u for u in units if u not in module_ids]
            if missing:
                raise TutorError(f"exam_units {missing} are not modules of {catalog['subject']}; add those "
                                 f"chapters to the catalog first (module ids: {module_ids})")
            clean["exam_units"] = list(dict.fromkeys(units))
        else:
            raise TutorError('exam_units must be "all" or a list of module ids')
    return clean


def rule_matches(when, answers):
    for key, expected in when.items():
        value = answers.get(key)
        options = expected if isinstance(expected, list) else [expected]
        if isinstance(value, list):
            if not any(v in options for v in value):
                return False
        elif value not in options:
            return False
    return True


def build_plan(catalog, answers):
    """Ordered plan rows from a subject catalog and the learner's answers for it.

    Every core module, then the chosen focus areas, then what the rules add; each module
    pulls in its requirements first. Rows follow catalog order; schedule_last goes last.
    """
    modules = {m["id"]: m for m in catalog["modules"]}
    order = [m["id"] for m in catalog["modules"]]
    areas = catalog.get("focus_areas", {})
    reasons = {}

    def add(mid, reason):
        if mid in reasons:
            return
        for req in modules[mid].get("requires", []):
            add(req, "Needed first")
        reasons[mid] = reason

    exam_units = answers.get("exam_units")
    if isinstance(exam_units, list):
        # the learner's exam decides the required syllabus; other core modules are left out
        for mid in exam_units:
            add(mid, "In your exam")
    else:
        for m in catalog["modules"]:
            if m["kind"] == "core":
                add(m["id"], "Core")
    for area in answers.get("focus", []):
        for mid in areas.get(area, {}).get("modules", []):
            add(mid, "Your choice")
    shorten = {}
    for rule in catalog.get("rules", []):
        if not rule_matches(rule["when"], answers):
            continue
        reason = rule.get("reason", "For your goal")
        for area in rule.get("add_focus", []):
            for mid in areas[area]["modules"]:
                add(mid, reason)
        for mid in rule.get("add_modules", []):
            add(mid, reason)
        if "shorten" in rule:
            for mid in rule["shorten"]["modules"]:
                shorten[mid] = (rule["shorten"]["hours"], rule.get("note", ""))

    last = catalog.get("schedule_last", [])
    chosen = [mid for mid in order if mid in reasons and mid not in last]
    chosen += [mid for mid in last if mid in reasons]
    rows = []
    for mid in chosen:
        hours, note = modules[mid]["hours"], ""
        if mid in shorten:
            cut, note = shorten[mid]
            hours = max(1, hours - cut)
        row = {"id": mid, "title": modules[mid]["title"], "hours": hours,
               "reason": reasons[mid], "note": note}
        if "weightage" in modules[mid]:
            row["weightage"] = modules[mid]["weightage"]
        rows.append(row)
    return rows


def prioritise(rows, catalog):
    """Reorder for a deadline that is too close: syllabus modules with the highest exam
    weightage first, extras after them, schedule_last at the end. Requirements still come
    before the modules that need them."""
    requires = {m["id"]: m.get("requires", []) for m in catalog["modules"]}
    last = set(catalog.get("schedule_last", []))
    order = {r["id"]: i for i, r in enumerate(rows)}
    required_reasons = {"Core", "In your exam", "Needed first"}

    def key(row):
        extra = row["reason"] not in required_reasons
        return (row["id"] in last, extra, -row.get("weightage", 0), order[row["id"]])

    placed, out = set(), []
    pending = sorted(rows, key=key)
    while pending:
        for row in pending:
            if all(req in placed or req not in order for req in requires.get(row["id"], [])):
                out.append(row)
                placed.add(row["id"])
                pending.remove(row)
                break
        else:  # a requirement cycle; keep the rest as they are
            out += pending
            break
    return out


def schedule(rows, start, hours_per_day):
    start = dt.date.fromisoformat(start)
    used = 0.0
    for row in rows:
        used += row["hours"]
        days = max(1, math.ceil(used / hours_per_day))
        row["target"] = (start + dt.timedelta(days=days - 1)).isoformat()
    return used, max(1, math.ceil(used / hours_per_day))


def plan_subject(subject, answers=None, root=None):
    """Build learner/subjects/<subject>/plan.json and plan.md. Keeps module statuses."""
    profile = read_json(learner_dir(root) / "profile.json")
    if profile is None:
        raise TutorError("no learner/profile.json yet; run onboard first")
    catalog = load_catalog(subject, root)
    folder = subject_dir(subject, root)
    if answers is None:
        answers = read_json(folder / "answers.json")
        if answers is None:
            raise TutorError(f"no saved answers for {subject}; pass --answers")
    answers = check_subject_answers(catalog, answers)
    write_json(folder / "answers.json", answers)

    old = read_json(folder / "plan.json", {})
    statuses = {r["id"]: r.get("status", "not-started") for r in old.get("modules", [])}
    start = answers.get("start_date") or old.get("start_date") or today()
    hours_per_day = answers.get("hours_per_day") or profile.get("hours_per_day") or 1
    rows = build_plan(catalog, answers)
    total_hours, total_days = schedule(rows, start, hours_per_day)
    deadline, available, fits, prioritised = None, None, True, False
    if answers.get("exam_date"):
        deadline = answers["exam_date"]
    elif answers.get("pace_weeks"):
        deadline = (dt.date.fromisoformat(start) + dt.timedelta(days=7 * answers["pace_weeks"])).isoformat()
    if deadline:
        days = max(0, (dt.date.fromisoformat(deadline) - dt.date.fromisoformat(start)).days)
        available = days * hours_per_day
        fits = total_hours <= available
        marking_scheme = (catalog.get("syllabus") or {}).get("marking_scheme")
        if not fits and marking_scheme and any("weightage" in r for r in rows):
            rows = prioritise(rows, catalog)
            schedule(rows, start, hours_per_day)
            prioritised = True
        for row in rows:
            row["before_deadline"] = row["target"] < deadline
    lesson_root = Path(root or ROOT) / "core" / "subjects" / subject
    for row in rows:
        row["status"] = statuses.get(row["id"], "not-started")
        row["lesson"] = f"core/subjects/{subject}/{row['id']}/lesson.json"
        row["written"] = (lesson_root / row["id"] / "lesson.json").exists()
    plan = {
        "subject": subject,
        "title": catalog.get("title", subject),
        "start_date": start,
        "hours_per_day": hours_per_day,
        "pace_weeks": answers.get("pace_weeks", 0),
        "board": answers.get("board"),
        "textbook": answers.get("textbook"),
        "edition": answers.get("edition"),
        "provisional": bool((catalog.get("syllabus") or {}).get("provisional")),
        "weightage_source": ((catalog.get("syllabus") or {}).get("marking_scheme") or {}).get("source"),
        "total_hours": total_hours,
        "total_days": total_days,
        "deadline": deadline,
        "available_hours": available,
        "fits": fits,
        "prioritised": prioritised,
        "modules": rows,
        "updated": today(),
    }
    write_json(folder / "plan.json", plan)
    (folder / "plan.md").write_text(render_plan(plan, catalog, answers), encoding="utf-8")
    progress = folder / "progress.md"
    if not progress.exists():
        progress.write_text(f"# Progress: {plan['title']}\n\n## Session history\n<!-- newest first -->\n",
                            encoding="utf-8")
    if subject not in profile.get("subjects", []):
        profile.setdefault("subjects", []).append(subject)
        write_json(learner_dir(root) / "profile.json", profile)
    return plan


def render_plan(plan, catalog, answers):
    labels = {}
    for q in catalog.get("questions", []):
        opts = {o["value"]: o["label"] for o in q["options"]}
        value = answers.get(q["id"])
        if value is not None:
            labels[q["question"]] = ", ".join(opts[v] for v in value) if isinstance(value, list) else opts[value]
    finish = plan["modules"][-1]["target"] if plan["modules"] else plan["start_date"]
    lines = [f"# Plan: {plan['title']}", "",
             f"_Built by `tools/learner.py plan {plan['subject']}` on {plan['updated']}._", ""]
    if labels:
        lines += ["## Your answers", ""] + [f"- **{q}** {a}" for q, a in labels.items()] + [""]
    lines += ["## Your path", "",
              f"{len(plan['modules'])} modules, about {plan['total_hours']:g} hours at "
              f"{plan['hours_per_day']:g} h/day: **{plan['total_days']} days**, target finish **{finish}**."]
    if plan.get("board") or plan.get("textbook"):
        book = " ".join(x for x in (plan.get("textbook"), f"({plan['edition']})" if plan.get("edition") else "") if x)
        lines.append(f"\nSyllabus: {' / '.join(x for x in (plan.get('board', '').upper(), book) if x)}.")
    if plan.get("provisional"):
        lines.append("\n> **Provisional plan.** It is not built from your textbook's contents page. "
                     "Please check the chapters with your teacher; the plan will be rebuilt from your book's list.")
    if plan.get("deadline") and not plan.get("fits"):
        short = plan["total_hours"] - plan["available_hours"]
        lines.append(f"\n> **Not enough time.** This needs about {plan['total_hours']:g} hours; until "
                     f"{plan['deadline']} there are about {plan['available_hours']:g} ({short:g} short). "
                     + (f"Ordered by exam weightage from {plan['weightage_source']}: the highest-mark "
                        "chapters come first. " if plan.get("prioritised") else
                        "With no official marking scheme, all chapters count as equal and keep the book's order. ")
                     + "More time per day, or fewer extras, would cover everything.")
        late = [r["title"] for r in plan["modules"] if not r.get("before_deadline", True)]
        if late:
            lines.append(f"> Won't fit before the deadline at this pace: {', '.join(late)}.")
    lines += ["", "| # | Module | Why | Marks | Hours | Target | Status |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(plan["modules"], 1):
        why = r["reason"] + (f" ({r['note']})" if r["note"] else "")
        marks = f"{r['weightage']:g}" if "weightage" in r else "-"
        lines.append(f"| {i} | {r['title']} | {why} | {marks} | {r['hours']:g} | {r['target']} | {r['status']} |")
    return "\n".join(lines) + "\n"


def set_progress(subject, module, status, root=None):
    check_choice("status", status, STATUSES)
    folder = subject_dir(subject, root)
    plan = read_json(folder / "plan.json")
    if plan is None:
        raise TutorError(f"no plan for {subject}; run plan first")
    for row in plan["modules"]:
        if row["id"] == module:
            row["status"] = status
            break
    else:
        raise TutorError(f"{module!r} is not in the {subject} plan")
    plan["updated"] = today()
    write_json(folder / "plan.json", plan)
    catalog = load_catalog(subject, root)
    (folder / "plan.md").write_text(render_plan(plan, catalog, read_json(folder / "answers.json", {})),
                                    encoding="utf-8")
    return plan


def next_module(plan):
    for status in ("in-progress", "not-started"):
        for row in plan["modules"]:
            if row["status"] == status:
                return row
    return None


def append_notes(subject, module, batch, extra=None, root=None):
    """Append a batch's revision notes (from its lesson) to learner/subjects/<s>/notes.md."""
    path = Path(root or ROOT) / "core" / "subjects" / subject / module / "lesson.json"
    lesson = read_json(path)
    if lesson is None:
        raise TutorError(f"no lesson at core/subjects/{subject}/{module}/lesson.json")
    batches = lesson.get("batches", [])
    if not 1 <= batch <= len(batches):
        raise TutorError(f"{module} has {len(batches)} batches; got batch {batch}")
    b = batches[batch - 1]
    notes = b.get("notes", {})
    lines = [f"## {lesson.get('title', module)} – {b.get('title', f'batch {batch}')}",
             f"_{today()}_", ""]
    lines += [f"- {p}" for p in notes.get("points", [])]
    if notes.get("code"):
        lines += ["", "```", notes["code"], "```"]
    if notes.get("remember"):
        lines += ["", f"**Remember:** {notes['remember']}"]
    if extra:
        lines += ["", f"**For you:** {' '.join(str(extra).split())}"]
    out = subject_dir(subject, root) / "notes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = "" if out.exists() else f"# Revision notes: {subject}\n\n"
    with out.open("a", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n\n")
    return out


def lesson_state(subject, module, root=None):
    lesson = read_json(Path(root or ROOT) / "core" / "subjects" / subject / module / "lesson.json")
    if lesson is None:
        return "not written yet"
    written, planned = len(lesson.get("batches", [])), len(lesson.get("planned_batches") or [])
    state = f"{written}/{planned} batches written" if planned and written < planned else "written"
    return state + (", unreviewed" if lesson.get("status") != "reviewed" else "")


def summary(root=None):
    profile = read_json(learner_dir(root) / "profile.json")
    if profile is None:
        return "No learner yet: run onboarding (core/teaching/onboarding.md)."
    model = read_json(learner_dir(root) / "model.json", {})
    lines = [f"Learner: {profile.get('name') or '(no name given)'} · {profile['age_band']} · "
             f"{profile['mode']} mode · explain in {profile['explain_language']} · "
             f"{profile['hours_per_day']:g} h/day"]
    if model:
        lines.append(f"Model: stage {model.get('journey_stage')}, pace {model.get('pace')}, "
                     f"styles {', '.join(model.get('preferred_styles', [])) or '-'}")
        if model.get("goals"):
            lines.append("Goals: " + "; ".join(model["goals"]))
        if model.get("weak_areas"):
            lines.append("Weak areas: " + ", ".join(model["weak_areas"]))
        if model.get("what_works"):
            lines.append("What works: " + "; ".join(model["what_works"]))
    for subject in profile.get("subjects", []):
        plan = read_json(subject_dir(subject, root) / "plan.json")
        if not plan:
            continue
        done = sum(r["status"] == "done" for r in plan["modules"])
        nxt = next_module(plan)
        nxt_text = (f"next: {nxt['title']} ({nxt['id']}, {lesson_state(subject, nxt['id'], root)})"
                    if nxt else "all modules done")
        lines.append(f"Subject {subject}: {done}/{len(plan['modules'])} done, {nxt_text}")
        if plan.get("board") or plan.get("textbook"):
            lines.append(f"  Syllabus: {plan.get('board') or '-'} / {plan.get('textbook') or '-'} "
                         f"({plan.get('edition') or 'edition?'})"
                         + (f", exam {plan['deadline']}" if plan.get("deadline") else ""))
        if plan.get("provisional"):
            lines.append("  PROVISIONAL plan (no contents page from the learner yet): say so; ask for the "
                         "textbook's chapter list or to check with their teacher, then rebuild.")
        if plan.get("deadline") and not plan.get("fits", True):
            late = [r["id"] for r in plan["modules"] if not r.get("before_deadline", True)]
            how = "ordered by weightage" if plan.get("prioritised") else "chapters treated as equal (no marking scheme)"
            lines.append(f"  Plan does not fit before {plan['deadline']}: needs {plan['total_hours']:g} h, "
                         f"{plan['available_hours']:g} h available; {how}. Won't fit: {', '.join(late) or '-'}")
    return "\n".join(lines)


# ---------- command line ----------

def pairs(values):
    out = []
    for item in values or []:
        if "=" not in item:
            raise TutorError(f"expected field=value, got {item!r}")
        key, value = item.split("=", 1)
        out.append((key.strip(), value.strip()))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("onboard", help="write profile and learner model")
    p.add_argument("--answers", required=True)
    p = sub.add_parser("plan", help="build or rebuild a subject plan")
    p.add_argument("subject")
    p.add_argument("--answers")
    p = sub.add_parser("progress", help="set a module's status")
    p.add_argument("subject")
    p.add_argument("module")
    p.add_argument("status", choices=STATUSES)
    p = sub.add_parser("model", help="update the learner model")
    p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    p.add_argument("--add", action="append", default=[], metavar="FIELD=VALUE")
    p.add_argument("--remove", action="append", default=[], metavar="FIELD=VALUE")
    p = sub.add_parser("notes", help="save a batch's revision notes")
    p.add_argument("subject")
    p.add_argument("module")
    p.add_argument("batch", type=int)
    p.add_argument("--extra")
    p = sub.add_parser("add-term", help="remember a personal term so it never leaves this machine")
    p.add_argument("term")
    sub.add_parser("init", help="create the adult learner id and signing key (done by onboard)")
    sub.add_parser("code", help="print the learner code, to show the learner once")
    p = sub.add_parser("restore", help="recreate the identity from a learner code")
    p.add_argument("learner_code")
    p = sub.add_parser("sharing", help="the learner's answer to the consent question")
    p.add_argument("state", choices=["on", "off"])
    sub.add_parser("mode", help="print adult or student")
    sub.add_parser("consent-sample", help="print the example record to show with the consent question")
    sub.add_parser("sharing-check", help="print the packages sharing still needs (nothing if ready)")
    sub.add_parser("install-sharing-packages", help="install them into .tutor/pylib (after the learner agrees)")
    sub.add_parser("show", help="summary for the start of a session")
    args = parser.parse_args(argv)

    # Success prints nothing (the learner must only ever see a tutor). onboard and plan
    # report bad answers on stderr so the agent can fix them silently; every other
    # failure goes to learner/tutor.log and, if a retry could help, to the retry queue.
    try:
        if args.cmd == "onboard":
            onboard(parse_answers(args.answers))
        elif args.cmd == "plan":
            plan_subject(args.subject, parse_answers(args.answers))
        elif args.cmd == "progress":
            set_progress(args.subject, args.module, args.status)
        elif args.cmd == "model":
            update_model(pairs(args.set), pairs(args.add), pairs(args.remove))
        elif args.cmd == "notes":
            append_notes(args.subject, args.module, args.batch, args.extra)
        elif args.cmd == "add-term":
            add_private_term(args.term)
        elif args.cmd == "show":
            print(summary())
        elif args.cmd == "init":
            init_identity()
        elif args.cmd == "code":
            code = learner_code()
            set_profile_flag("code_shown", True)
            print(f"{code}\n{CODE_WARNING}")
        elif args.cmd == "restore":
            restore_identity(args.learner_code)
        elif args.cmd == "sharing":
            set_sharing(args.state == "on")
        elif args.cmd == "mode":
            print((read_json(learner_dir() / "profile.json") or {}).get("mode", "none"))
        elif args.cmd == "sharing-check":
            missing = missing_packages()
            if missing:
                print(" ".join(missing))
        elif args.cmd == "install-sharing-packages":
            install_packages()
        elif args.cmd == "consent-sample":
            import collect
            print(collect.consent_sample(read_json(learner_dir() / "profile.json", {}).get("mode", "adult")))
    except Exception as exc:
        tutorlog.log(ROOT, "learner", f"{args.cmd} failed: {exc}")
        if args.cmd in ("onboard", "plan", "restore", "code", "consent-sample", "install-sharing-packages",
                        "sharing"):
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not isinstance(exc, TutorError):
            tutorlog.queue(ROOT, "cli", {"tool": "learner", "args": list(argv if argv is not None else sys.argv[1:])})
    return 0

if __name__ == "__main__":
    sys.exit(main())
