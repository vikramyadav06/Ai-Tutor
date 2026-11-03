#!/usr/bin/env python3
"""
Check that the course content is complete and well-formed.

    python tools/validate_course.py                      # check everything
    python tools/validate_course.py --changed-from main  # also check a PR only touches shared course files

Used by contributors' AI agents before committing, by the GitHub Actions check on every
pull request, and by maintainers when reviewing. Standard library only.
Exit code 0 = all good, 1 = problems found (listed in the output).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEP_FIELDS = {
    "learn": ["title", "body"],
    "choice": ["question", "options", "answer", "explain"],
    "fill": ["prompt", "code", "answers", "explain"],
    "order": ["prompt", "items", "explain"],
    "practice": ["title", "body", "file", "command", "solution"],
}
# Paths a course contribution may change. Personal files (learner/, my-work/) never belong in a PR.
ALLOWED_PREFIXES = ("course/", "README.md", "CURRICULUM.md", "requirements.txt")
FORBIDDEN_PREFIXES = ("learner/", "my-work/", ".env")


def check_lesson(mid, lesson, errors):
    where = f"course/{mid}/lesson.json"
    if lesson.get("id") != mid:
        errors.append(f"{where}: 'id' is {lesson.get('id')!r}, expected {mid!r}")
    for key in ("title", "intro", "batches"):
        if not lesson.get(key):
            errors.append(f"{where}: missing '{key}'")
    for bi, batch in enumerate(lesson.get("batches", []), 1):
        at = f"{where} batch {bi}"
        steps = batch.get("steps", [])
        if not batch.get("title"):
            errors.append(f"{at}: missing 'title'")
        if not 2 <= len(steps) <= 8:
            errors.append(f"{at}: has {len(steps)} steps; keep batches to 2-8 small steps")
        notes = batch.get("notes") or {}
        if not notes.get("points") or not notes.get("remember"):
            errors.append(f"{at}: 'notes' needs 'points' and 'remember' (revision notes are required)")
        for si, step in enumerate(steps, 1):
            here = f"{at} step {si}"
            kind = step.get("type")
            if kind not in STEP_FIELDS:
                errors.append(f"{here}: unknown type {kind!r}")
                continue
            for field in STEP_FIELDS[kind]:
                if field not in step or step[field] in ("", [], None):
                    errors.append(f"{here} ({kind}): missing '{field}'")
            if kind == "choice" and isinstance(step.get("options"), list):
                ans = step.get("answer")
                if not isinstance(ans, int) or not 0 <= ans < len(step["options"]):
                    errors.append(f"{here}: 'answer' must be an index into 'options'")
            if kind == "fill" and "code" in step:
                blanks = step["code"].count("___")
                if blanks == 0:
                    errors.append(f"{here}: 'code' has no ___ blanks")
                if blanks != len(step.get("answers", [])):
                    errors.append(f"{here}: {blanks} blanks but {len(step.get('answers', []))} answer lists")
            if kind == "order" and len(step.get("items", [])) < 3:
                errors.append(f"{here}: 'order' needs at least 3 items")
            if kind == "practice":
                for field in ("file", "solution"):
                    path = step.get(field)
                    if path and not (ROOT / path).exists():
                        errors.append(f"{here}: {field} {path} does not exist")
    for qi, item in enumerate(lesson.get("interview", []), 1):
        if not item.get("q") or not item.get("a"):
            errors.append(f"{where} interview {qi}: needs 'q' and 'a'")


def check_bundle(catalog, errors):
    bundle_path = ROOT / "course" / "bundle.js"
    if not bundle_path.exists():
        errors.append("course/bundle.js is missing: run python tools/build_bundle.py")
        return
    text = bundle_path.read_text(encoding="utf-8")
    try:
        data = json.loads(text.split("window.COURSE_BUNDLE = ", 1)[1].rstrip().rstrip(";"))
    except (IndexError, json.JSONDecodeError):
        errors.append("course/bundle.js can't be read: run python tools/build_bundle.py")
        return
    for m in catalog["modules"]:
        lesson = ROOT / m["folder"] / "lesson.json"
        if lesson.exists():
            current = json.loads(lesson.read_text(encoding="utf-8"))
            if data.get("lessons", {}).get(m["id"]) != current:
                errors.append(f"course/bundle.js is out of date for '{m['id']}': run python tools/build_bundle.py")


def check_changed_paths(base, errors):
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        errors.append(f"could not list changed files against {base}: {exc}")
        return
    for path in out:
        if path.startswith(FORBIDDEN_PREFIXES):
            errors.append(f"{path}: personal files must never be in a contribution")
        elif not path.startswith(ALLOWED_PREFIXES):
            errors.append(f"{path}: outside course content; needs a maintainer to review separately")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed-from", metavar="BASE", help="git ref to compare changed files against")
    args = parser.parse_args()

    errors = []
    try:
        catalog = json.loads((ROOT / "course" / "catalog.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"course/catalog.json is not valid JSON: {exc}")
        return 1

    ids = [m["id"] for m in catalog["modules"]]
    if len(ids) != len(set(ids)):
        errors.append("course/catalog.json: duplicate module ids")
    for m in catalog["modules"]:
        for req in m.get("requires", []):
            if req not in ids:
                errors.append(f"catalog: {m['id']} requires unknown module {req!r}")
        if m["folder"] != f"course/{m['id']}":
            errors.append(f"catalog: {m['id']} folder should be course/{m['id']}")
    for area, spec in catalog["focus_areas"].items():
        for mid in spec["modules"]:
            if mid not in ids:
                errors.append(f"catalog: focus area {area!r} lists unknown module {mid!r}")

    written = 0
    for m in catalog["modules"]:
        path = ROOT / m["folder"] / "lesson.json"
        if not path.exists():
            continue
        written += 1
        try:
            lesson = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{m['folder']}/lesson.json is not valid JSON: {exc}")
            continue
        check_lesson(m["id"], lesson, errors)
        for sub in ("exercises", "solutions"):
            for f in (ROOT / m["folder"] / sub).glob("*.py"):
                try:
                    compile(f.read_text(encoding="utf-8"), str(f), "exec")
                except SyntaxError as exc:
                    errors.append(f"{f.relative_to(ROOT)}: syntax error: {exc}")

    check_bundle(catalog, errors)
    if args.changed_from:
        check_changed_paths(args.changed_from, errors)

    if errors:
        print(f"Found {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Course OK: {written} of {len(ids)} modules written, all checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
