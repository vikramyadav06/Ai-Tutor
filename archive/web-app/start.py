#!/usr/bin/env python3
"""
Personal onboarding for the Playwright + Python course.

    python start.py          # answer a few questions, get your personal plan
    python start.py --plan   # rebuild your plan from learner/profile.json

Creates (in the learner/ folder, which is private and not committed by default):
    profile.json   - your answers
    my-plan.md     - your personal, ordered learning plan with target dates
    progress.md    - your progress tracker (created once, never overwritten)

Uses only the Python standard library, so it runs before anything is installed.
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "course" / "catalog.json"
LEARNER = ROOT / "learner"
PROFILE = LEARNER / "profile.json"
PLAN = LEARNER / "my-plan.md"
PROGRESS = LEARNER / "progress.md"

ROLES = [
    ("manual-qa", "Manual tester / QA"),
    ("automation-qa", "Automation QA (Selenium, Cypress, etc.)"),
    ("developer", "Developer"),
    ("student", "Student / fresher"),
    ("other", "Other"),
]
PYTHON_LEVELS = [
    ("none", "New to Python"),
    ("basic", "Basic (variables, functions, loops)"),
    ("comfortable", "Comfortable (classes, modules, pytest)"),
]
SELENIUM_LEVELS = [
    ("none", "Never used it"),
    ("some", "Some experience"),
    ("strong", "Use it regularly / professionally"),
]
GOALS = [
    ("job-switch", "Switch jobs / prepare for interviews"),
    ("use-at-work", "Use Playwright in my current job"),
    ("migrate", "Migrate existing Selenium tests to Playwright"),
    ("career-start", "Start a career in test automation"),
    ("explore", "Just exploring / learning for fun"),
]
PACES = [
    ("2", "Fast: about 2 weeks"),
    ("4", "Steady: about 4 weeks"),
    ("8", "Relaxed: about 8 weeks"),
    ("0", "No deadline"),
]
STYLES = [
    ("hands-on", "Mostly hands-on, short theory"),
    ("balanced", "Balanced"),
    ("theory-first", "Explain concepts well before coding"),
]

# ---------- input helpers ----------

def ask_text(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip() or default
        if value:
            return value
        print("  Please enter a value.")


def ask_choice(prompt, options, default=None):
    print(f"\n{prompt}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}) {label}")
    hint = f" [{default}]" if default else ""
    while True:
        raw = input(f"Choose 1-{len(options)}{hint}: ").strip() or (str(default) if default else "")
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print("  Please type one of the numbers shown.")


def ask_multi(prompt, options):
    print(f"\n{prompt}")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}) {label}")
    print(f"  {len(options) + 1}) All of the above")
    print("  (press Enter to skip)")
    while True:
        raw = input("Choose numbers separated by commas, e.g. 1,3: ").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",")]
        if all(p.isdigit() and 1 <= int(p) <= len(options) + 1 for p in parts):
            if str(len(options) + 1) in parts:
                return [key for key, _ in options]
            return [options[int(p) - 1][0] for p in parts]
        print("  Please type numbers from the list, separated by commas.")


def ask_hours():
    while True:
        raw = input("\nHow many hours per day can you study? [2]: ").strip() or "2"
        try:
            hours = float(raw)
            if 0.5 <= hours <= 12:
                return hours
        except ValueError:
            pass
        print("  Please enter a number between 0.5 and 12.")


# ---------- onboarding ----------

def interview(catalog):
    print("=" * 60)
    print(" Welcome to the Playwright + Python course!")
    print(" A few questions so your plan fits you. Takes ~2 minutes.")
    print("=" * 60 + "\n")

    focus_options = [(k, v["label"]) for k, v in catalog["focus_areas"].items()]
    profile = {
        "name": ask_text("What's your name?"),
        "role": ask_choice("What best describes your current role?", ROLES),
        "python_level": ask_choice("How comfortable are you with Python?", PYTHON_LEVELS),
        "selenium_level": ask_choice("Have you used Selenium?", SELENIUM_LEVELS),
        "goal": ask_choice("What's your main goal?", GOALS),
        "focus": ask_multi(
            "Beyond the core lessons, which topics do you want to learn?", focus_options
        ),
        "hours_per_day": ask_hours(),
        "pace_weeks": int(ask_choice("How fast do you want to go?", PACES, default=2)),
        "learning_style": ask_choice("How do you like to learn?", STYLES, default=2),
        "language": ask_text("\nPreferred language for explanations", default="English"),
        "notes": input("\nAnything else? (a specific job description, deadline, topic) [skip]: ").strip(),
        "start_date": dt.date.today().isoformat(),
    }
    return profile


# ---------- plan building ----------

def build_plan(profile, catalog):
    """Same rules as the web app: all of them come from catalog.json -> rules."""
    rules = catalog["rules"]
    modules = {m["id"]: m for m in catalog["modules"]}
    order = [m["id"] for m in catalog["modules"]]
    reasons = {}

    def add(mid, reason):
        if mid in reasons:
            return
        for req in modules[mid]["requires"]:
            add(req, "Needed first")
        reasons[mid] = reason

    primer = rules["python_primer"]
    if profile.get("python_level") == primer["when_python_level"]:
        add(primer["module"], "Python foundation")
    for m in catalog["modules"]:
        if m["kind"] == "core":
            add(m["id"], "Core")

    extras = rules["goal_extras"].get(profile.get("goal"), {"focus": [], "modules": []})
    for area in profile.get("focus", []):
        for mid in catalog["focus_areas"].get(area, {}).get("modules", []):
            add(mid, "Your choice")
    for area in extras["focus"]:
        for mid in catalog["focus_areas"][area]["modules"]:
            add(mid, "For your goal")
    for mid in extras["modules"]:
        add(mid, "For your goal")

    last = rules["schedule_last"]
    chosen = [mid for mid in order if mid in reasons and mid not in last]
    chosen += [mid for mid in last if mid in reasons]

    quick = rules["quick_pace"]
    is_quick = all(profile.get(k) == v for k, v in quick["when"].items())
    rows = []
    for mid in chosen:
        m = modules[mid]
        hours = m["hours"]
        note = ""
        if is_quick and mid in quick["modules"]:
            hours = max(1, hours - quick["hours_saved"])
            note = quick["note"]
        rows.append({"id": mid, "title": m["title"], "folder": m["folder"],
                     "hours": hours, "reason": reasons[mid], "note": note})
    return rows


def schedule(rows, profile):
    start = dt.date.fromisoformat(profile.get("start_date") or dt.date.today().isoformat())
    per_day = float(profile.get("hours_per_day") or 2)
    used = 0.0
    for row in rows:
        used += row["hours"]
        days = max(1, math.ceil(used / per_day))
        row["target"] = (start + dt.timedelta(days=days - 1)).isoformat()
    total_days = max(1, math.ceil(used / per_day))
    return used, total_days


def render_plan(profile, rows, total_hours, total_days):
    labels = lambda opts, key: dict(opts).get(key, key)
    lines = [
        f"# {profile['name']}'s Playwright Learning Plan",
        "",
        f"_Generated by `start.py` on {dt.date.today().isoformat()}. "
        "Re-run `python start.py` to change your answers, or edit `learner/profile.json` "
        "and run `python start.py --plan`._",
        "",
        "## About you",
        "",
        f"- **Role:** {labels(ROLES, profile['role'])}",
        f"- **Python:** {labels(PYTHON_LEVELS, profile['python_level'])}",
        f"- **Selenium:** {labels(SELENIUM_LEVELS, profile['selenium_level'])}",
        f"- **Goal:** {labels(GOALS, profile['goal'])}",
        f"- **Time:** {profile['hours_per_day']:g} h/day, learning style: "
        f"{labels(STYLES, profile['learning_style']).lower()}",
        f"- **Explanations in:** {profile.get('language', 'English')}",
    ]
    if profile.get("notes"):
        lines.append(f"- **Notes:** {profile['notes']}")

    finish = rows[-1]["target"] if rows else profile["start_date"]
    lines += [
        "",
        "## Your path",
        "",
        f"{len(rows)} modules, about {total_hours:g} hours: **{total_days} days**, "
        f"target finish **{finish}**.",
    ]
    pace = int(profile.get("pace_weeks") or 0)
    if pace and total_days > pace * 7:
        needed = total_hours / (pace * 7)
        lines.append(
            f"\n> To finish in {pace} weeks you'd need about {needed:.1f} h/day, "
            "or choose fewer focus topics."
        )
    lines += [
        "",
        "| # | Module | Why | Hours | Target date | Lesson |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i, r in enumerate(rows, 1):
        why = r["reason"] + (f" ({r['note']})" if r["note"] else "")
        lines.append(
            f"| {i} | {r['title']} | {why} | {r['hours']} | {r['target']} | "
            f"[{r['folder']}](../{r['folder']}/lesson.json) |"
        )
    lines += [
        "",
        "If a lesson link doesn't open yet, that module hasn't been written; "
        "see the course index in README.md.",
        "",
        "Track what you finish in [progress.md](progress.md).",
        "",
    ]
    return "\n".join(lines)


def render_progress(profile, rows):
    lines = [
        f"# {profile['name']}'s Progress",
        "",
        "## Current status",
        f"- Current module: {rows[0]['title'] if rows else '-'}",
        f"- Started: {profile['start_date']}",
        "- Last session: -",
        "",
        "## Modules",
        "| # | Module | Status | Quiz |",
        "| --- | --- | --- | --- |",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['title']} | Not started | - |")
    lines += [
        "",
        "## Weak areas to revisit",
        "- (none yet)",
        "",
        "## Session history",
        "<!-- newest first -->",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Personal onboarding and learning plan.")
    parser.add_argument("--plan", action="store_true",
                        help="rebuild my-plan.md from learner/profile.json without asking questions")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    LEARNER.mkdir(exist_ok=True)

    if args.plan:
        if not PROFILE.exists():
            sys.exit("No learner/profile.json yet. Run `python start.py` first.")
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    else:
        if PROFILE.exists():
            again = input("A profile already exists. Start over with new answers? [y/N]: ")
            if again.strip().lower() != "y":
                profile = json.loads(PROFILE.read_text(encoding="utf-8"))
                print("Keeping your existing profile.")
            else:
                profile = interview(catalog)
        else:
            profile = interview(catalog)
        PROFILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rows = build_plan(profile, catalog)
    total_hours, total_days = schedule(rows, profile)
    PLAN.write_text(render_plan(profile, rows, total_hours, total_days), encoding="utf-8")
    if not PROGRESS.exists():
        PROGRESS.write_text(render_progress(profile, rows), encoding="utf-8")
        progress_note = "created"
    else:
        progress_note = "kept as is, your history is safe"

    print("\n" + "=" * 60)
    print(f" Done, {profile['name']}! Your plan: {len(rows)} modules, ~{total_days} days.")
    print(f"   Plan:     {PLAN.relative_to(ROOT)}")
    print(f"   Progress: {PROGRESS.relative_to(ROOT)} ({progress_note})")
    print(" Next: open learner/my-plan.md and start with the first module.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCancelled. Run `python start.py` again any time.")
