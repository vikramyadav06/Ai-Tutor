"""The private learner model: updates, notes after batches, private terms, plan rules."""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BASE = {"age_band": "18-24", "level": "college", "preferred_styles": ["examples"]}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def onboarded(tutor_root, learner_tool):
    learner_tool.onboard(BASE, root=tutor_root)
    return tutor_root


def test_model_add_remove_set(onboarded, learner_tool):
    lt = learner_tool
    lt.update_model(adds=[("weak_areas", "fractions"), ("weak_areas", "decimals")], root=onboarded)
    lt.update_model(sets=[("pace", "slow"), ("journey_stage", "beginner")], root=onboarded)
    lt.update_model(adds=[("strengths", "fractions")], removes=[("weak_areas", "decimals")], root=onboarded)
    model = read(onboarded / "learner" / "model.json")
    assert model["pace"] == "slow" and model["journey_stage"] == "beginner"
    assert model["strengths"] == ["fractions"]
    assert model["weak_areas"] == []  # a topic can't be a strength and a weak area at once


def test_model_rejects_bad_values(onboarded, learner_tool):
    with pytest.raises(learner_tool.TutorError, match="topic slugs"):
        learner_tool.update_model(adds=[("weak_areas", "Long Division!")], root=onboarded)
    with pytest.raises(learner_tool.TutorError, match="pace must be one of"):
        learner_tool.update_model(sets=[("pace", "warp")], root=onboarded)
    with pytest.raises(learner_tool.TutorError, match="unknown model field"):
        learner_tool.update_model(sets=[("school", "x")], root=onboarded)


def test_model_lists_are_capped_keeping_newest(onboarded, learner_tool):
    for i in range(12):
        learner_tool.update_model(adds=[("what_works", f"idea {i}")], root=onboarded)
    model = read(onboarded / "learner" / "model.json")
    assert len(model["what_works"]) == 10
    assert model["what_works"][-1] == "idea 11" and "idea 0" not in model["what_works"]


def test_model_cli(onboarded, run_tool):
    run_tool("learner", "model", "--add", "weak_areas=photosynthesis", "--set", "pace=fast",
             "--add", "what_works=real-life examples, then the formula")
    model = read(onboarded / "learner" / "model.json")
    assert model["weak_areas"] == ["photosynthesis"]
    assert model["pace"] == "fast"
    assert model["what_works"] == ["real-life examples, then the formula"]


def test_notes_after_batch(onboarded, learner_tool):
    path = learner_tool.append_notes("class-9-science", "matter", 1, extra="Hot vs cold food smell helped.",
                                     root=onboarded)
    learner_tool.append_notes("class-9-science", "matter", 2, root=onboarded)
    text = path.read_text(encoding="utf-8")
    assert path == onboarded / "learner" / "subjects" / "class-9-science" / "notes.md"
    assert text.startswith("# Revision notes: class-9-science")
    assert "## Matter in our surroundings – What matter is" in text
    assert "- Matter has mass and takes up space." in text
    assert "**Remember:** Matter = mass + space, made of moving particles." in text
    assert "**For you:** Hot vs cold food smell helped." in text
    assert text.index("What matter is") < text.index("States of matter")
    with pytest.raises(learner_tool.TutorError, match="has 2 batches"):
        learner_tool.append_notes("class-9-science", "matter", 3, root=onboarded)


def test_private_terms_deduplicate(onboarded, learner_tool):
    learner_tool.add_private_term("Springfield High", root=onboarded)
    learner_tool.add_private_term("springfield high", root=onboarded)
    learner_tool.add_private_term("  Acme   Corp ", root=onboarded)
    assert read(onboarded / "learner" / "private_terms.json")["terms"] == ["Springfield High", "Acme Corp"]


def test_show_without_learner(tutor_root, learner_tool):
    assert "run onboarding" in learner_tool.summary(root=tutor_root)


def test_progress_unknown_module(onboarded, learner_tool):
    learner_tool.plan_subject("python", {}, root=onboarded)
    with pytest.raises(learner_tool.TutorError, match="not in the python plan"):
        learner_tool.set_progress("python", "rocket-science", "done", root=onboarded)


def test_python_quick_pace_rule(onboarded, learner_tool):
    plan = learner_tool.plan_subject("python", {"prior": "other-language", "start_date": "2026-11-03"},
                                     root=onboarded)
    hours = {m["id"]: (m["hours"], m["note"]) for m in plan["modules"]}
    assert hours["first-steps"] == (1, "Quick pace: you've programmed before")  # never below 1 hour
    assert hours["values-and-variables"] == (1, "Quick pace: you've programmed before")
    assert hours["functions"] == (3, "")


def test_playwright_plans_match_old_start_py(learner_tool):
    """The old start.py's hard-coded rules are now catalog data; plans must not change."""
    catalog = learner_tool.load_catalog("playwright-python")
    cases = json.loads((FIXTURES / "start_py_plans.json").read_text(encoding="utf-8"))
    assert len(cases) == 135
    for case in cases:
        rows = learner_tool.build_plan(catalog, case["answers"])
        assert [[r["id"], r["hours"], r["reason"], r["note"]] for r in rows] == case["rows"], case["answers"]
