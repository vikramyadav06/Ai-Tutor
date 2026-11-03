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
SUBJECT_EXTRA_KEYS = {"pace_weeks", "hours_per_day", "start_date"}


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
    write_json(learner_dir(root) / "profile.json", profile)
    write_json(learner_dir(root) / "model.json", model)
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
    if "start_date" in answers:
        try:
            clean["start_date"] = dt.date.fromisoformat(answers["start_date"]).isoformat()
        except (TypeError, ValueError):
            raise TutorError("start_date must be YYYY-MM-DD")
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
        rows.append({"id": mid, "title": modules[mid]["title"], "hours": hours,
                     "reason": reasons[mid], "note": note})
    return rows


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
        "total_hours": total_hours,
        "total_days": total_days,
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
    pace = plan.get("pace_weeks") or 0
    if pace and plan["total_days"] > pace * 7:
        lines.append(f"\n> To finish in {pace} weeks you'd need about "
                     f"{plan['total_hours'] / (pace * 7):.1f} h/day, or a shorter plan.")
    lines += ["", "| # | Module | Why | Hours | Target | Status |", "| --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(plan["modules"], 1):
        why = r["reason"] + (f" ({r['note']})" if r["note"] else "")
        lines.append(f"| {i} | {r['title']} | {why} | {r['hours']:g} | {r['target']} | {r['status']} |")
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
        nxt_text = (f"next: {nxt['title']} ({nxt['id']}, {'written' if nxt['written'] else 'not written yet'})"
                    if nxt else "all modules done")
        lines.append(f"Subject {subject}: {done}/{len(plan['modules'])} done, {nxt_text}")
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
    sub.add_parser("show", help="summary for the start of a session")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "onboard":
            profile, _ = onboard(parse_answers(args.answers))
            print(f"Profile saved ({profile['mode']} mode).")
        elif args.cmd == "plan":
            plan = plan_subject(args.subject, parse_answers(args.answers))
            print(f"Plan saved: {len(plan['modules'])} modules, ~{plan['total_days']} days "
                  f"-> learner/subjects/{args.subject}/plan.md")
        elif args.cmd == "progress":
            set_progress(args.subject, args.module, args.status)
            print("Progress updated.")
        elif args.cmd == "model":
            update_model(pairs(args.set), pairs(args.add), pairs(args.remove))
            print("Learner model updated.")
        elif args.cmd == "notes":
            append_notes(args.subject, args.module, args.batch, args.extra)
            print("Notes saved.")
        elif args.cmd == "add-term":
            add_private_term(args.term)
            print("Saved.")
        elif args.cmd == "show":
            print(summary())
    except TutorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
