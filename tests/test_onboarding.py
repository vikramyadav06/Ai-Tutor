"""TECH_SPEC §14 Phase 1: onboarding for two invented learners (an adult learning Python,
a 14-year-old learning Class 9 science) produces correct profiles and plans."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

ADULT = {
    "name": "Arjun Mehta",
    "age_band": "25-34",
    "level": "professional",
    "explain_language": "en",
    "goals": ["Automate reports at work"],
    "journey_stage": "new",
    "preferred_styles": ["hands-on", "examples"],
    "pace": "steady",
    "hours_per_day": 1.5,
}
ADULT_PYTHON = {"prior": "none", "goal": "automation", "pace_weeks": 4, "start_date": "2026-11-03"}

STUDENT = {
    "name": "Pinky",
    "age_band": "13-17",
    "level": "secondary",
    "explain_language": "hi",
    "goals": ["Score well in the final exam"],
    "journey_stage": "beginner",
    "preferred_styles": ["visual", "analogies"],
    "pace": "slow",
    "hours_per_day": 1,
}
STUDENT_SCIENCE = {"goal": "exam", "focus": ["practice"], "board": "cbse",
                   "textbook": "Exploration (NCERT Science, Class 9)", "edition": "2026-27",
                   "exam_units": "all", "exam_date": "2027-03-01", "start_date": "2026-11-03"}
SUBJECT = "class-9-science-exploration"  # catalog built from the learner's pasted contents page


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_adult_learning_python(tutor_root, run_tool):
    run_tool("learner", "onboard", "--answers", json.dumps(ADULT))
    run_tool("learner", "plan", "python", "--answers", json.dumps(ADULT_PYTHON))
    learner = tutor_root / "learner"

    profile = read(learner / "profile.json")
    assert profile["mode"] == "adult"
    assert profile["age_band"] == "25-34"
    assert profile["level"] == "professional"
    assert profile["explain_language"] == "en"
    assert profile["hours_per_day"] == 1.5
    assert profile["sharing"] is False
    assert profile["subjects"] == ["python"]

    model = read(learner / "model.json")
    assert model["goals"] == ["Automate reports at work"]
    assert model["preferred_styles"] == ["hands-on", "examples"]
    assert model["pace"] == "steady" and model["journey_stage"] == "new"
    assert model["strengths"] == model["weak_areas"] == model["what_works"] == []

    plan = read(learner / "subjects" / "python" / "plan.json")
    assert [(m["id"], m["reason"]) for m in plan["modules"]] == [
        ("first-steps", "Core"),
        ("values-and-variables", "Core"),
        ("control-flow", "Core"),
        ("functions", "Core"),
        ("collections", "Core"),
        ("files", "For your goal"),
    ]
    assert plan["total_hours"] == 14
    assert plan["total_days"] == 10  # 14 h at 1.5 h/day
    assert plan["modules"][0]["target"] == "2026-11-03"
    assert plan["modules"][-1]["target"] == "2026-11-12"
    assert all(m["status"] == "not-started" for m in plan["modules"])
    assert (learner / "subjects" / "python" / "plan.md").exists()
    assert (learner / "subjects" / "python" / "progress.md").exists()

    # the name stays local, as private terms
    assert read(learner / "private_terms.json")["terms"] == ["Arjun Mehta", "Arjun", "Mehta"]
    # adults get an anonymous identity at onboarding (TECH_SPEC §4), readable only by them
    identity_file = tutor_root / ".tutor" / "identity.json"
    identity = read(identity_file)
    assert set(identity) == {"learner_id", "signing_seed_b64", "created"}
    assert identity["learner_id"].startswith("lrn-") and "arjun" not in identity["learner_id"]
    assert identity_file.stat().st_mode & 0o777 == 0o600


def test_fourteen_year_old_learning_class_9_science(tutor_root, run_tool):
    run_tool("learner", "onboard", "--answers", json.dumps(STUDENT))
    run_tool("learner", "plan", SUBJECT, "--answers", json.dumps(STUDENT_SCIENCE))
    learner = tutor_root / "learner"

    profile = read(learner / "profile.json")
    assert profile["mode"] == "student"
    assert profile["age_band"] == "13-17"
    assert profile["level"] == "secondary"
    assert profile["explain_language"] == "hi"

    plan = read(learner / "subjects" / SUBJECT / "plan.json")
    # every chapter of the learner's own book, in its order, then the chosen extra and revision last
    chapters = [f"chapter-{i:02d}" for i in range(1, 14)]
    assert [m["id"] for m in plan["modules"]] == chapters + ["extra-practice", "exam-revision"]
    assert {m["reason"] for m in plan["modules"][:13]} == {"Core"}
    assert plan["total_hours"] == 39 and plan["deadline"] == "2027-03-01"
    assert plan["fits"] is True and plan["prioritised"] is False and plan["provisional"] is False
    assert plan["board"] == "cbse" and plan["edition"] == "2026-27"
    assert all(m["before_deadline"] for m in plan["modules"])
    first = plan["modules"][0]
    assert first["written"] is True and first["lesson"] == f"core/subjects/{SUBJECT}/chapter-01/lesson.json"
    assert "weightage" not in first  # no official marking scheme given: chapters count as equal
    assert plan["modules"][1]["written"] is False

    # student mode: no identity; only a separate random secret for multi-device sync
    assert not (tutor_root / ".tutor" / "identity.json").exists()
    sync_file = tutor_root / ".tutor" / "sync.json"
    assert set(read(sync_file)) == {"sync_secret_b64", "created"}
    assert sync_file.stat().st_mode & 0o777 == 0o600


def test_two_subjects_for_one_learner(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    learner_tool.plan_subject("python", ADULT_PYTHON, root=tutor_root)
    learner_tool.plan_subject("playwright-python", {"python_level": "basic", "selenium_level": "none",
                                                    "goal": "explore", "focus": []}, root=tutor_root)
    profile = read(tutor_root / "learner" / "profile.json")
    assert profile["subjects"] == ["python", "playwright-python"]
    text = learner_tool.summary(root=tutor_root)
    assert "Subject python: 0/6 done, next: First steps" in text
    assert "Subject playwright-python: 0/6 done, next: Setup" in text


@pytest.mark.parametrize("band,mode", [("under-13", "student"), ("13-17", "student"), ("18-24", "adult"),
                                       ("25-34", "adult"), ("55+", "adult")])
def test_mode_follows_age_band(tutor_root, learner_tool, band, mode):
    profile, _ = learner_tool.onboard({"age_band": band, "level": "self-learner"}, root=tutor_root)
    assert profile["mode"] == mode


@pytest.mark.parametrize("answers,message", [
    ({"level": "college"}, "age_band is required"),
    ({"age_band": "18-24"}, "level is required"),
    ({"age_band": "17", "level": "college"}, "age_band must be one of"),
    ({"age_band": "18-24", "level": "college", "birth_date": "2001-01-01"}, "unknown onboarding fields"),
    ({"age_band": "18-24", "level": "college", "explain_language": "English"}, "BCP-47"),
    ({"age_band": "18-24", "level": "college", "preferred_styles": ["telepathy"]}, "preferred_styles must be one of"),
    ({"age_band": "18-24", "level": "college", "goals": ["x" * 201]}, "at most 200"),
    ({"age_band": "18-24", "level": "college", "hours_per_day": 30}, "hours_per_day"),
])
def test_bad_onboarding_answers_are_rejected(tutor_root, learner_tool, answers, message):
    with pytest.raises(learner_tool.TutorError, match=message):
        learner_tool.onboard(answers, root=tutor_root)
    assert not (tutor_root / "learner" / "profile.json").exists()


def test_bad_subject_answers_are_rejected(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="goal must be one of"):
        learner_tool.plan_subject("python", {"goal": "fame"}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="unknown answers"):
        learner_tool.plan_subject("python", {"email": "a@b.c"}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="no catalog"):
        learner_tool.plan_subject("astrology", {}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="not a slug"):
        learner_tool.plan_subject("../../etc", {}, root=tutor_root)


def test_cli_reports_errors_without_traceback(run_tool):
    result = run_tool("learner", "onboard", "--answers", '{"level": "college"}', check=False)
    assert result.returncode == 2
    assert "error: age_band is required" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_replanning_keeps_progress(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    learner_tool.plan_subject("python", ADULT_PYTHON, root=tutor_root)
    learner_tool.set_progress("python", "first-steps", "done", root=tutor_root)
    learner_tool.set_progress("python", "values-and-variables", "in-progress", root=tutor_root)
    plan = learner_tool.plan_subject("python", {**ADULT_PYTHON, "goal": "career"}, root=tutor_root)
    status = {m["id"]: m["status"] for m in plan["modules"]}
    assert status["first-steps"] == "done"
    assert status["values-and-variables"] == "in-progress"
    assert [m["id"] for m in plan["modules"]][-2:] == ["testing", "project"]
    assert learner_tool.next_module(plan)["id"] == "values-and-variables"
    # saved answers are reused when none are given
    again = learner_tool.plan_subject("python", root=tutor_root)
    assert [m["id"] for m in again["modules"]] == [m["id"] for m in plan["modules"]]


def test_reonboarding_keeps_what_was_learned(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    learner_tool.update_model(adds=[("weak_areas", "loops"), ("what_works", "short analogies")], root=tutor_root)
    learner_tool.onboard({**ADULT, "pace": "fast"}, root=tutor_root)
    model = read(tutor_root / "learner" / "model.json")
    assert model["pace"] == "fast"
    assert model["weak_areas"] == ["loops"] and model["what_works"] == ["short analogies"]


def test_close_exam_without_marking_scheme_keeps_book_order(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    units = [f"chapter-{i:02d}" for i in range(1, 7)]
    plan = learner_tool.plan_subject(SUBJECT, {
        "goal": "exam", "focus": ["practice"], "board": "cbse", "exam_units": units,
        "exam_date": "2026-11-17", "start_date": "2026-11-03"}, root=tutor_root)
    ids = [m["id"] for m in plan["modules"]]
    # only the exam's chapters (plus extras), in the book's order: no invented weightage
    assert ids == units + ["extra-practice", "exam-revision"]
    assert plan["fits"] is False and plan["prioritised"] is False
    assert plan["total_hours"] == 21 and plan["available_hours"] == 14
    late = [m["id"] for m in plan["modules"] if not m["before_deadline"]]
    assert late == ["chapter-06", "extra-practice", "exam-revision"]
    text = (tutor_root / "learner" / "subjects" / SUBJECT / "plan.md").read_text()
    assert "Not enough time" in text and "all chapters count as equal" in text


def with_marking_scheme(root):
    path = root / "core" / "subjects" / SUBJECT / "catalog.json"
    catalog = json.loads(path.read_text())
    catalog["syllabus"]["marking_scheme"] = {"source": "official marking scheme provided by the learner (test data)"}
    for m, marks in zip(catalog["modules"], [4, 4, 6, 6, 10, 10, 5, 5, 6, 6, 4, 4, 10]):
        m["weightage"] = marks
    path.write_text(json.dumps(catalog))


def test_close_exam_with_official_marking_scheme_prioritises(tutor_root, learner_tool):
    with_marking_scheme(tutor_root)
    learner_tool.onboard(STUDENT, root=tutor_root)
    units = [f"chapter-{i:02d}" for i in range(1, 7)]
    plan = learner_tool.plan_subject(SUBJECT, {"goal": "exam", "exam_units": units,
                                               "exam_date": "2026-11-15", "start_date": "2026-11-03"}, root=tutor_root)
    ids = [m["id"] for m in plan["modules"]]
    assert plan["prioritised"] is True
    assert ids == ["chapter-05", "chapter-06", "chapter-03", "chapter-04", "chapter-01", "chapter-02", "exam-revision"]
    text = (tutor_root / "learner" / "subjects" / SUBJECT / "plan.md").read_text()
    assert "Ordered by exam weightage from official marking scheme provided by the learner" in text


def test_plan_must_follow_the_learners_own_book(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="build a catalog from the learner's own chapter list"):
        learner_tool.plan_subject(SUBJECT, {"textbook": "Science for Class IX", "edition": "2019"}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="board must be one of"):
        learner_tool.plan_subject(SUBJECT, {"board": "Delhi University"}, root=tutor_root)


def test_provisional_plan_says_so(tutor_root, learner_tool):
    path = tutor_root / "core" / "subjects" / SUBJECT / "catalog.json"
    catalog = json.loads(path.read_text())
    catalog["syllabus"]["provisional"] = True
    path.write_text(json.dumps(catalog))
    learner_tool.onboard(STUDENT, root=tutor_root)
    plan = learner_tool.plan_subject(SUBJECT, {"goal": "exam"}, root=tutor_root)
    assert plan["provisional"] is True
    assert "Provisional plan" in (tutor_root / "learner" / "subjects" / SUBJECT / "plan.md").read_text()
    assert "PROVISIONAL plan" in learner_tool.summary(root=tutor_root)


def test_whole_syllabus_by_default(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    plan = learner_tool.plan_subject(SUBJECT, {"goal": "understand"}, root=tutor_root)
    assert len(plan["modules"]) == 13 and plan["deadline"] is None and plan["fits"] is True


def test_unknown_exam_unit_is_rejected(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="add those chapters to the catalog first"):
        learner_tool.plan_subject(SUBJECT, {"exam_units": ["chapter-01", "chapter-99"]}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="exam_date must be YYYY-MM-DD"):
        learner_tool.plan_subject(SUBJECT, {"exam_date": "March"}, root=tutor_root)


# ---------- the language a learner asked for is remembered ----------

def test_onboarding_with_a_language_mix(tutor_root, learner_tool):
    profile, _ = learner_tool.onboard({**ADULT, "explain_language": ["hi", "en"],
                                       "language_note": "Hindi explanations, English technical terms"},
                                      root=tutor_root)
    assert profile["explain_language"] == "hi" and profile["explain_languages"] == ["hi", "en"]
    text = learner_tool.summary(root=tutor_root)
    assert "Teach in: Hindi (hi) + English (en), Hindi explanations, English technical terms." in text
    assert "use it from the first message of every session" in text


def test_a_language_change_mid_course_survives_the_next_session(tutor_root, run_tool, learner_tool):
    """The bug: 'teach in Hindi and English' was followed in the conversation but never saved,
    so the next session went back to English."""
    run_tool("learner", "onboard", "--answers", json.dumps(ADULT))  # onboarded in English
    record = {"subject": "python", "module": "first-steps", "language": {"languages": ["hi", "en"]},
              "steps": [{"step_ref": "b1-s1", "type": "learn", "outcome": "viewed"}]}
    result = run_tool("tutor", "record", "--json", json.dumps(record))
    assert result.stdout == "" and result.stderr == ""
    profile = read(tutor_root / "learner" / "profile.json")
    assert profile["explain_languages"] == ["hi", "en"] and profile["explain_language"] == "hi"
    # the next session's private context says so
    start = subprocess.run([sys.executable, str(REPO / "tools" / "tutor.py"), "hook", "session-start"],
                           input='{"source": "startup"}', capture_output=True, text=True,
                           env={**os.environ, "TUTOR_ROOT": str(tutor_root)}, cwd=tutor_root)
    context = json.loads(start.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Teach in: Hindi (hi) + English (en) mixed." in context
    # and back to one language, from the command line too
    run_tool("learner", "language", "en")
    assert "Teach in: English (en)." in learner_tool.summary(root=tutor_root)


def test_bad_languages_are_rejected(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    for bad in (["Hindi"], ["hi", "en", "ta", "te"], []):
        with pytest.raises(learner_tool.TutorError):
            learner_tool.set_language(bad, root=tutor_root)
    assert read(tutor_root / "learner" / "profile.json")["explain_language"] == "en"


def test_old_profiles_without_a_language_list_still_read(tutor_root, learner_tool):
    learner_tool.onboard(ADULT, root=tutor_root)
    path = tutor_root / "learner" / "profile.json"
    profile = read(path)
    for key in ("explain_languages", "language_note"):
        profile.pop(key)
    path.write_text(json.dumps(profile))
    assert "Teach in: English (en)." in learner_tool.summary(root=tutor_root)
