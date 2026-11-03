"""TECH_SPEC §14 Phase 1: onboarding for two invented learners (an adult learning Python,
a 14-year-old learning Class 9 science) produces correct profiles and plans."""
import json

import pytest

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
STUDENT_SCIENCE = {"goal": "exam", "focus": ["physics"], "board": "CBSE", "syllabus": "NCERT Science Class 9",
                   "exam_units": "all", "exam_date": "2027-03-01", "start_date": "2026-11-03"}


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

    # the name stays local, as private terms; no identity is created in Phase 1
    assert read(learner / "private_terms.json")["terms"] == ["Arjun Mehta", "Arjun", "Mehta"]
    assert not (tutor_root / ".tutor").exists()


def test_fourteen_year_old_learning_class_9_science(tutor_root, run_tool):
    run_tool("learner", "onboard", "--answers", json.dumps(STUDENT))
    run_tool("learner", "plan", "class-9-science", "--answers", json.dumps(STUDENT_SCIENCE))
    learner = tutor_root / "learner"

    profile = read(learner / "profile.json")
    assert profile["mode"] == "student"
    assert profile["age_band"] == "13-17"
    assert profile["level"] == "secondary"
    assert profile["explain_language"] == "hi"

    plan = read(learner / "subjects" / "class-9-science" / "plan.json")
    # the whole syllabus, in textbook order, then the chosen extra and revision last
    assert [(m["id"], m["reason"]) for m in plan["modules"]] == [
        ("matter", "Core"), ("is-matter-pure", "Core"), ("atoms-and-molecules", "Core"),
        ("structure-of-the-atom", "Core"), ("the-cell", "Core"), ("tissues", "Core"), ("motion", "Core"),
        ("force-and-laws", "Core"), ("gravitation", "Core"), ("work-and-energy", "Core"), ("sound", "Core"),
        ("food-resources", "Core"), ("numericals-practice", "Your choice"), ("exam-revision", "For your goal"),
    ]
    assert plan["total_hours"] == 36 and plan["deadline"] == "2027-03-01"
    assert plan["fits"] is True and plan["prioritised"] is False
    assert plan["board"] == "CBSE" and plan["syllabus"] == "NCERT Science Class 9"
    assert all(m["before_deadline"] for m in plan["modules"])
    matter = plan["modules"][0]
    assert matter["written"] is True and matter["lesson"] == "core/subjects/class-9-science/matter/lesson.json"
    assert matter["weightage"] == 5
    assert plan["modules"][1]["written"] is False

    # student mode: no identity of any kind
    assert not (tutor_root / ".tutor").exists()


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


def test_exam_units_and_a_close_exam_prioritise_by_weightage(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    units = ["matter", "atoms-and-molecules", "the-cell", "motion", "force-and-laws", "gravitation"]
    plan = learner_tool.plan_subject("class-9-science", {
        "goal": "exam", "focus": ["physics"], "board": "CBSE", "exam_units": units,
        "exam_date": "2026-11-17", "start_date": "2026-11-03"}, root=tutor_root)
    ids = [m["id"] for m in plan["modules"]]
    # only the exam's chapters (plus extras); chapters outside the exam are left out
    assert set(ids) == set(units) | {"numericals-practice", "exam-revision"}
    assert "sound" not in ids and "tissues" not in ids
    assert plan["fits"] is False and plan["prioritised"] is True
    assert plan["total_hours"] == 21 and plan["available_hours"] == 14
    # highest marks first, but a chapter's prerequisites still come before it
    assert ids == ["the-cell", "matter", "atoms-and-molecules", "motion", "force-and-laws", "gravitation",
                   "numericals-practice", "exam-revision"]
    late = [m["id"] for m in plan["modules"] if not m["before_deadline"]]
    assert late == ["gravitation", "numericals-practice", "exam-revision"]
    text = (tutor_root / "learner" / "subjects" / "class-9-science" / "plan.md").read_text()
    assert "Not enough time" in text and "Ordered by exam weightage" in text
    assert "Won't fit before the deadline at this pace: Gravitation" in text


def test_whole_syllabus_by_default(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    plan = learner_tool.plan_subject("class-9-science", {"goal": "understand"}, root=tutor_root)
    assert len(plan["modules"]) == 12 and plan["deadline"] is None and plan["fits"] is True


def test_unknown_exam_unit_is_rejected(tutor_root, learner_tool):
    learner_tool.onboard(STUDENT, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="add those chapters to the catalog first"):
        learner_tool.plan_subject("class-9-science", {"exam_units": ["matter", "chapter-99"]}, root=tutor_root)
    with pytest.raises(learner_tool.TutorError, match="exam_date must be YYYY-MM-DD"):
        learner_tool.plan_subject("class-9-science", {"exam_date": "March"}, root=tutor_root)
