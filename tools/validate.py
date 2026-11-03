#!/usr/bin/env python3
"""
Check subjects and lessons: format, completeness and prompt-injection risks.

    python tools/validate.py                          # every subject in core/subjects/index.json
    python tools/validate.py core/subjects/<id>       # one subject folder
    python tools/validate.py path/to/lesson.json      # one lesson (e.g. a freshly generated one)

Used by tutors after writing a lesson, by CI on every pull request, and by reviewers.
Lesson content is data: this tool never runs anything from it.
If learner/private_terms.json exists, lessons are also checked for the learner's personal
terms (generated lessons must be generic).

Exit code 0 = all good, 1 = problems found (listed in the output). Standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "core" / "subjects" / "index.json"
ALLOWED_HOSTS = ROOT / "core" / "allowed_hosts.txt"
PRIVATE_TERMS = ROOT / "learner" / "private_terms.json"

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
LEVELS = {"primary", "middle", "secondary", "college", "postgraduate", "professional", "self-learner"}
KINDS = {"core", "focus", "optional"}
# TECH_SPEC §12: the only command an agent may run from a lesson.
PRACTICE_COMMAND = re.compile(r"^(python -m )?pytest [\w./ -]+$")

REQUIRED = {
    "learn": ["title", "body"],
    "choice": ["question", "options", "answer", "explain"],
    "fill": ["prompt", "answers", "explain"],
    "order": ["prompt", "items", "explain"],
    "practice": ["title", "body"],
    "explain": ["prompt", "rubric"],
}

# TECH_SPEC §12: text that looks like instructions to an AI, or like commands to run.
INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)", re.I), "'ignore previous'"),
    (re.compile(r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)", re.I), "'disregard previous'"),
    (re.compile(r"system\s+prompt", re.I), "'system prompt'"),
    (re.compile(r"you\s+are\s+now\b", re.I), "'you are now'"),
    (re.compile(r"new\s+instructions", re.I), "'new instructions'"),
    (re.compile(r"run\s+this\s+command", re.I), "'run this command'"),
    (re.compile(r"(?<![\w-])curl(?![\w-])", re.I), "curl"),
    (re.compile(r"(?<![\w-])wget(?![\w-])", re.I), "wget"),
    (re.compile(r"rm\s+-[a-z]*r[a-z]*f|rm\s+-[a-z]*f[a-z]*r", re.I), "'rm -rf'"),
    (re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"), "base64-like blob over 200 characters"),
]
URL = re.compile(r"\b(?:https?|ftp)://[^\s)\"'<>\]]+", re.I)


def load_allowed_hosts():
    hosts = set()
    if ALLOWED_HOSTS.exists():
        for line in ALLOWED_HOSTS.read_text(encoding="utf-8").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                hosts.add(line)
    return hosts


def load_private_terms(path=PRIVATE_TERMS):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    terms = data.get("terms", []) if isinstance(data, dict) else data
    return [t for t in terms if isinstance(t, str) and t.strip()]


def host_allowed(host, allowed):
    host = (host or "").lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allowed)


def iter_strings(obj, where=""):
    """Yield (location, text) for every string anywhere in a JSON value."""
    if isinstance(obj, str):
        yield where, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(v, f"{where}.{k}" if where else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_strings(v, f"{where}[{i}]")


def scan_text(label, obj, allowed_hosts, private_terms, flags):
    """Flag prompt-injection risks, unknown links and private terms in any string."""
    term_patterns = [(t, re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I)) for t in private_terms]
    for where, text in iter_strings(obj):
        at = f"{label} {where}".strip()
        for pattern, name in INJECTION_PATTERNS:
            if pattern.search(text):
                flags.append(f"{at}: contains {name} (instruction-like text; needs manual review)")
        for url in URL.findall(text):
            host = urlsplit(url).hostname
            if not host_allowed(host, allowed_hosts):
                flags.append(f"{at}: links to {host or url!r}, not in core/allowed_hosts.txt")
        for term, pattern in term_patterns:
            if pattern.search(text):
                flags.append(f"{at}: contains a private term from learner/private_terms.json; lessons must be generic")


def check_lesson(lesson, errors, *, where, module_id=None, subject_id=None, check_files=True):
    if not isinstance(lesson, dict):
        errors.append(f"{where}: lesson must be a JSON object")
        return
    for key in ("id", "title", "subject", "level", "explain_language", "intro", "batches"):
        if not lesson.get(key):
            errors.append(f"{where}: missing '{key}'")
    if lesson.get("id") and not SLUG.match(str(lesson["id"])):
        errors.append(f"{where}: 'id' {lesson['id']!r} is not a slug")
    if module_id and lesson.get("id") != module_id:
        errors.append(f"{where}: 'id' is {lesson.get('id')!r}, expected {module_id!r} (the folder name)")
    if subject_id and lesson.get("subject") != subject_id:
        errors.append(f"{where}: 'subject' is {lesson.get('subject')!r}, expected {subject_id!r}")
    if lesson.get("level") and lesson["level"] not in LEVELS:
        errors.append(f"{where}: 'level' {lesson['level']!r} must be one of {sorted(LEVELS)}")
    if lesson.get("explain_language") and not LANG.match(str(lesson["explain_language"])):
        errors.append(f"{where}: 'explain_language' must be a BCP-47 tag such as 'en' or 'hi-IN'")

    batches = lesson.get("batches") if isinstance(lesson.get("batches"), list) else []
    for bi, batch in enumerate(batches, 1):
        at = f"{where} batch {bi}"
        steps = batch.get("steps", []) if isinstance(batch, dict) else []
        if not isinstance(batch, dict) or not batch.get("title"):
            errors.append(f"{at}: missing 'title'")
            if not isinstance(batch, dict):
                continue
        if not 2 <= len(steps) <= 8:
            errors.append(f"{at}: has {len(steps)} steps; keep batches to 2-8 small steps")
        notes = batch.get("notes") or {}
        if not isinstance(notes, dict) or not notes.get("points") or not notes.get("remember"):
            errors.append(f"{at}: 'notes' needs 'points' and 'remember' (revision notes are required)")
        for si, step in enumerate(steps, 1):
            check_step(step, errors, f"{at} step {si}", check_files)

    for qi, item in enumerate(lesson.get("interview", []) or [], 1):
        if not isinstance(item, dict) or not item.get("q") or not item.get("a"):
            errors.append(f"{where} interview {qi}: needs 'q' and 'a'")


def empty(value):
    return value is None or value == "" or value == [] or value == {}


def check_step(step, errors, here, check_files):
    if not isinstance(step, dict):
        errors.append(f"{here}: step must be a JSON object")
        return
    kind = step.get("type")
    if kind not in REQUIRED:
        errors.append(f"{here}: unknown type {kind!r}; use one of {sorted(REQUIRED)}")
        return
    for field in REQUIRED[kind]:
        if empty(step.get(field)):
            errors.append(f"{here} ({kind}): missing '{field}'")

    if kind == "choice" and isinstance(step.get("options"), list):
        ans = step.get("answer")
        if isinstance(ans, bool) or not isinstance(ans, int) or not 0 <= ans < len(step["options"]):
            errors.append(f"{here}: 'answer' must be an index into 'options'")
    if kind == "fill":
        has_code, has_text = not empty(step.get("code")), not empty(step.get("text"))
        if has_code == has_text:
            errors.append(f"{here} (fill): needs exactly one of 'code' or 'text'")
        else:
            body = step.get("code") if has_code else step.get("text")
            blanks = str(body).count("___")
            answers = step.get("answers") if isinstance(step.get("answers"), list) else []
            if blanks == 0:
                errors.append(f"{here}: no ___ blanks")
            elif blanks != len(answers):
                errors.append(f"{here}: {blanks} blanks but {len(answers)} answer lists")
            if any(not isinstance(a, list) or not a for a in answers):
                errors.append(f"{here}: each entry in 'answers' must be a non-empty list of accepted answers")
    if kind == "order" and isinstance(step.get("items"), list) and len(step["items"]) < 3:
        errors.append(f"{here}: 'order' needs at least 3 items")
    if kind == "explain":
        rubric = step.get("rubric")
        if not empty(rubric) and (not isinstance(rubric, list) or not all(isinstance(r, str) and r for r in rubric)):
            errors.append(f"{here} (explain): 'rubric' must be a list of points")
    if kind == "practice":
        command = step.get("command")
        if command is not None and not PRACTICE_COMMAND.match(str(command)):
            errors.append(f"{here}: practice 'command' {command!r} is not allowed; "
                          "only `pytest <paths/flags>` (optionally `python -m pytest ...`)")
        for field in ("file", "solution"):
            path = step.get(field)
            if path is None:
                continue
            rel = Path(str(path))
            if rel.is_absolute() or ".." in rel.parts:
                errors.append(f"{here}: {field} must be a path inside the repo")
            elif check_files and not (ROOT / rel).exists():
                errors.append(f"{here}: {field} {path} does not exist")


def check_catalog(subject_id, catalog, errors, where):
    if not isinstance(catalog, dict):
        errors.append(f"{where}: catalog must be a JSON object")
        return []
    if catalog.get("subject") != subject_id:
        errors.append(f"{where}: 'subject' is {catalog.get('subject')!r}, expected {subject_id!r}")
    for key in ("title", "modules"):
        if not catalog.get(key):
            errors.append(f"{where}: missing '{key}'")
    for level in catalog.get("levels", []):
        if level not in LEVELS:
            errors.append(f"{where}: unknown level {level!r}")
    modules = [m for m in catalog.get("modules", []) if isinstance(m, dict)]
    ids = [m.get("id") for m in modules]
    if len(ids) != len(set(ids)):
        errors.append(f"{where}: duplicate module ids")
    for m in modules:
        mid = m.get("id")
        if not isinstance(mid, str) or not SLUG.match(mid):
            errors.append(f"{where}: module id {mid!r} is not a slug")
        if not m.get("title"):
            errors.append(f"{where}: module {mid!r} missing 'title'")
        if not isinstance(m.get("hours"), (int, float)) or m["hours"] <= 0:
            errors.append(f"{where}: module {mid!r} needs positive 'hours'")
        if m.get("kind") not in KINDS:
            errors.append(f"{where}: module {mid!r} 'kind' must be one of {sorted(KINDS)}")
        for req in m.get("requires", []):
            if req not in ids:
                errors.append(f"{where}: {mid} requires unknown module {req!r}")
    areas = catalog.get("focus_areas", {}) or {}
    for area, spec in areas.items():
        for mid in spec.get("modules", []):
            if mid not in ids:
                errors.append(f"{where}: focus area {area!r} lists unknown module {mid!r}")
    question_ids = set()
    for q in catalog.get("questions", []) or []:
        qid = q.get("id") if isinstance(q, dict) else None
        if not qid or not q.get("question") or not q.get("options"):
            errors.append(f"{where}: each question needs 'id', 'question' and 'options'")
            continue
        question_ids.add(qid)
        for opt in q["options"]:
            if not isinstance(opt, dict) or "value" not in opt or "label" not in opt:
                errors.append(f"{where}: question {qid!r} options need 'value' and 'label'")
    for ri, rule in enumerate(catalog.get("rules", []) or [], 1):
        if not isinstance(rule, dict) or not isinstance(rule.get("when"), dict) or not rule["when"]:
            errors.append(f"{where}: rule {ri} needs a non-empty 'when'")
            continue
        for mid in rule.get("add_modules", []) + rule.get("shorten", {}).get("modules", []):
            if mid not in ids:
                errors.append(f"{where}: rule {ri} names unknown module {mid!r}")
        for area in rule.get("add_focus", []):
            if area not in areas:
                errors.append(f"{where}: rule {ri} names unknown focus area {area!r}")
    for mid in catalog.get("schedule_last", []) or []:
        if mid not in ids:
            errors.append(f"{where}: schedule_last names unknown module {mid!r}")
    return ids


def read_json(path, errors):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{rel(path)}: not found")
    except json.JSONDecodeError as exc:
        errors.append(f"{rel(path)}: not valid JSON: {exc}")
    return None


def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def check_subject(folder, errors, flags, allowed_hosts, private_terms):
    folder = Path(folder)
    subject_id = folder.name
    catalog = read_json(folder / "catalog.json", errors)
    if catalog is None:
        return 0
    ids = check_catalog(subject_id, catalog, errors, rel(folder / "catalog.json"))
    scan_text(rel(folder / "catalog.json"), catalog, allowed_hosts, private_terms, flags)
    written = 0
    for mid in ids:
        path = folder / str(mid) / "lesson.json"
        if not path.exists():
            continue
        written += 1
        lesson = read_json(path, errors)
        if lesson is None:
            continue
        check_lesson(lesson, errors, where=rel(path), module_id=mid, subject_id=subject_id)
        scan_text(rel(path), lesson, allowed_hosts, private_terms, flags)
        for sub in ("exercises", "solutions"):
            for f in sorted((folder / str(mid) / sub).glob("*.py")):
                try:
                    compile(f.read_text(encoding="utf-8"), str(f), "exec")
                except SyntaxError as exc:
                    errors.append(f"{rel(f)}: syntax error: {exc}")
    return written


def check_index(errors):
    index = read_json(INDEX, errors)
    if index is None:
        return []
    folders = []
    seen = set()
    for entry in index.get("subjects", []):
        sid = entry.get("id")
        if not isinstance(sid, str) or not SLUG.match(sid):
            errors.append(f"core/subjects/index.json: subject id {sid!r} is not a slug")
            continue
        if sid in seen:
            errors.append(f"core/subjects/index.json: duplicate subject {sid!r}")
        seen.add(sid)
        if entry.get("path") != f"core/subjects/{sid}":
            errors.append(f"core/subjects/index.json: {sid} path should be core/subjects/{sid}")
        if not entry.get("title"):
            errors.append(f"core/subjects/index.json: {sid} missing 'title'")
        for level in entry.get("levels", []):
            if level not in LEVELS:
                errors.append(f"core/subjects/index.json: {sid} has unknown level {level!r}")
        folder = ROOT / "core" / "subjects" / sid
        if not (folder / "catalog.json").exists():
            errors.append(f"core/subjects/index.json: {sid} has no {sid}/catalog.json")
        else:
            folders.append(folder)
    for folder in sorted((ROOT / "core" / "subjects").iterdir()):
        if folder.is_dir() and (folder / "catalog.json").exists() and folder.name not in seen:
            errors.append(f"core/subjects/{folder.name}: not listed in core/subjects/index.json")
    return folders


def validate(targets=None, private_terms_path=PRIVATE_TERMS):
    """Return (errors, flags, summary). Used by main() and by tests."""
    errors, flags = [], []
    allowed_hosts = load_allowed_hosts()
    private_terms = load_private_terms(private_terms_path)
    lessons = subjects = 0
    if not targets:
        for folder in check_index(errors):
            subjects += 1
            lessons += check_subject(folder, errors, flags, allowed_hosts, private_terms)
    for target in targets or []:
        path = Path(target)
        if path.is_dir():
            subjects += 1
            lessons += check_subject(path, errors, flags, allowed_hosts, private_terms)
        else:
            lesson = read_json(path, errors)
            if lesson is not None:
                lessons += 1
                in_subject = path.parent.parent.parent.name == "subjects"
                check_lesson(lesson, errors, where=rel(path),
                             module_id=path.parent.name if in_subject else None,
                             subject_id=path.parent.parent.name if in_subject else None)
                scan_text(rel(path), lesson, allowed_hosts, private_terms, flags)
    return errors, flags, f"{subjects} subject(s), {lessons} lesson(s)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="subject folders or lesson.json files (default: all subjects)")
    args = parser.parse_args(argv)
    errors, flags, summary = validate(args.targets)
    if errors:
        print(f"Found {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
    if flags:
        print(f"Flagged {len(flags)} item(s) for manual review:")
        for f in flags:
            print(f"  - {f}")
    if errors or flags:
        return 1
    print(f"OK: {summary} checked, no problems.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
