"""The learner must only ever experience a tutor: background work is silent, never fails
loudly, and is retried next session (owner requirement, see TECH_SPEC §15)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

PROFILE = {"name": "Pinky", "age_band": "13-17", "level": "secondary", "explain_language": "en",
           "goals": ["Do well in the final exam"], "preferred_styles": ["visual"], "pace": "steady"}

BATCH_1 = {
    "subject": "class-9-science-exploration", "module": "chapter-01", "agent": "claude-code",
    "steps": [
        {"step_ref": "b1-s1", "type": "learn", "outcome": "viewed", "seconds": 20},
        {"step_ref": "b1-s2", "type": "choice", "outcome": "incorrect", "attempts": 2, "hints": 1, "seconds": 70},
        {"step_ref": "b1-s3", "type": "learn", "outcome": "viewed"},
        {"step_ref": "b1-s4", "type": "fill", "outcome": "correct", "time_band": "30s-2m"},
        {"step_ref": "b1-s5", "type": "explain", "outcome": "correct", "answer_text": "Hot particles move faster"},
    ],
    "moves": [{"topic": "diffusion", "move": "analogy", "style": "analogies", "worked": True}],
    "signals": [{"kind": "confused", "topic": "matter"}],
    "private_terms": ["Sunrise Public School"],
    "batch_done": 1,
    "notes_extra": "Air is matter too: it has mass.",
    "model": {"add": {"weak_areas": ["particles"], "what_works": ["everyday examples before the rule"]}},
}
BATCH_2 = {
    "subject": "class-9-science-exploration", "module": "chapter-01",
    "steps": [{"step_ref": "b2-s2", "type": "order", "outcome": "correct"},
              {"step_ref": "b2-s5", "type": "practice", "outcome": "correct", "seconds": 600}],
    "exercises": [{"ref": "melting-ice", "passed": "true"}],
    "batch_done": 2,
    "module_done": True,
    "model": {"add": {"strengths": ["particles"]}, "set": {"journey_stage": "beginner"}},
    "progress_entry": "### 2026-11-03 – Matter in our surroundings\n- Learned: matter, particles, states\n- Next: Atoms and molecules",
    "feedback": {"rating": 5},
    "end": True,
}


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def learner_repo(tutor_root):
    """tutor_root as a git repo, like a learner's clone."""
    (tutor_root / "my-work").mkdir()
    (tutor_root / "my-work" / "README.md").write_text("your code\n")
    git(tutor_root, "init", "-q")
    git(tutor_root, "add", "-A")
    git(tutor_root, "-c", "user.name=x", "-c", "user.email=x@invalid", "commit", "-q", "-m", "clone")
    return tutor_root


def assert_silent(result):
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"stdout: {result.stdout!r}"
    assert result.stderr == "", f"stderr: {result.stderr!r}"


def hook(run_tool, tutor_root, event, stdin):
    env = {**os.environ, "TUTOR_ROOT": str(tutor_root)}
    return subprocess.run([sys.executable, str(REPO / "tools" / "tutor.py"), "hook", event],
                          input=json.dumps(stdin), capture_output=True, text=True, env=env, cwd=tutor_root)


def test_full_session_is_silent(learner_repo, run_tool):
    """Simulate a learner's first session exactly as Claude Code runs it: hooks at start and
    end, onboarding, then one record call per batch. Nothing may write to stdout or stderr,
    except the start hook's context, which Claude Code hands to the agent only."""
    root = learner_repo

    start = hook(run_tool, root, "session-start", {"source": "startup", "hook_event_name": "SessionStart"})
    assert start.returncode == 0 and start.stderr == ""
    ctx = json.loads(start.stdout)  # only structured context for the agent, nothing else
    assert set(ctx) == {"hookSpecificOutput"}
    assert ctx["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "start onboarding" in ctx["hookSpecificOutput"]["additionalContext"]

    assert_silent(run_tool("learner", "onboard", "--answers", json.dumps(PROFILE)))
    assert_silent(run_tool("learner", "plan", "class-9-science-exploration", "--answers", '{"goal": "exam", "focus": ["practice"]}'))
    assert_silent(run_tool("tutor", "record", "--json", json.dumps(BATCH_1)))
    (root / "my-work" / "matter").mkdir()
    (root / "my-work" / "matter" / "ice-observations.md").write_text("Temperature stayed at 0 °C\n")
    assert_silent(run_tool("tutor", "record", "--json", json.dumps(BATCH_2)))
    assert_silent(hook(run_tool, root, "session-end", {"reason": "prompt_input_exit"}))

    learner = root / "learner"
    assert not (learner / "tutor.log").exists()  # nothing failed
    assert not (learner / "pending.jsonl").exists()

    # everything was recorded
    sessions = list((learner / "sessions").glob("*.jsonl"))
    assert len(sessions) == 1
    events = [json.loads(line) for line in sessions[0].read_text().splitlines()]
    kinds = [e["event"] for e in events]
    assert kinds.count("step") == 7 and kinds.count("batch") == 2
    assert kinds[0] == "start" and kinds[-1] == "end" and kinds.count("end") == 1
    assert events[0]["agent"] == "claude-code"
    assert not (learner / "sessions" / "current").exists()

    notes = (learner / "subjects" / "class-9-science-exploration" / "notes.md").read_text()
    assert "What matter is" in notes and "States of matter" in notes
    assert "**For you:** Air is matter too: it has mass." in notes
    plan = json.loads((learner / "subjects" / "class-9-science-exploration" / "plan.json").read_text())
    assert plan["modules"][0]["status"] == "done"
    model = json.loads((learner / "model.json").read_text())
    assert model["strengths"] == ["particles"] and model["weak_areas"] == []
    assert model["what_works"] == ["everyday examples before the rule"]
    assert model["journey_stage"] == "beginner"
    terms = json.loads((learner / "private_terms.json").read_text())["terms"]
    assert "Sunrise Public School" in terms and "Pinky" in terms
    progress = (learner / "subjects" / "class-9-science-exploration" / "progress.md").read_text()
    assert "### 2026-11-03 – Matter in our surroundings" in progress

    # the learner's work was committed locally, only my-work/ and core/subjects/
    log = git(root, "log", "--format=%s", "-2").splitlines()
    assert log[0] == "tutor: save work and lessons"
    changed = git(root, "show", "--name-only", "--format=", "HEAD").split()
    assert changed == ["my-work/matter/ice-observations.md"]
    assert not [f for f in git(root, "ls-files").split() if f.startswith(("learner/", ".tutor/"))]

    # the next session starts with private context built from what was recorded
    nxt = hook(run_tool, root, "session-start", {"source": "startup"})
    text = json.loads(nxt.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "Pinky" in text and "next: Chapter 2 (placeholder title)" in text and "Never read it out" in text
    assert (learner / "agent.txt").read_text().strip() == "claude-code"


def test_failures_are_logged_and_retried_next_session(learner_repo, run_tool, learner_tool):
    root = learner_repo
    learner_tool.onboard(PROFILE, root=root)
    learner_tool.plan_subject("class-9-science-exploration", {"goal": "exam"}, root=root)
    # break the notes file: a directory where notes.md should be
    notes = root / "learner" / "subjects" / "class-9-science-exploration" / "notes.md"
    notes.mkdir()

    assert_silent(run_tool("tutor", "record", "--json", json.dumps(
        {"subject": "class-9-science-exploration", "module": "chapter-01", "batch_done": 1, "notes_extra": "x",
         "steps": [{"step_ref": "b1-s1", "type": "learn", "outcome": "viewed"}]})))
    assert "will retry next session" in (root / "learner" / "tutor.log").read_text()
    pending = [json.loads(line) for line in (root / "learner" / "pending.jsonl").read_text().splitlines()]
    assert pending[0]["kind"] == "record" and pending[0]["payload"]["batch_done"] == 1
    assert "steps" not in pending[0]["payload"]  # the step was logged; only the failure is retried

    notes.rmdir()  # the problem goes away
    start = hook(run_tool, root, "session-start", {"source": "startup"})
    assert start.returncode == 0 and start.stderr == ""
    assert "What matter is" in notes.read_text()
    assert not (root / "learner" / "pending.jsonl").exists()


def test_retries_give_up_after_three_attempts(learner_repo, tutor_tool, learner_tool):
    root = learner_repo
    learner_tool.onboard(PROFILE, root=root)
    learner_tool.plan_subject("class-9-science-exploration", {}, root=root)
    notes = root / "learner" / "subjects" / "class-9-science-exploration" / "notes.md"
    notes.mkdir()  # stays broken
    tutor_tool.record({"subject": "class-9-science-exploration", "module": "chapter-01", "batch_done": 1}, root=root)
    for _ in range(4):
        tutor_tool.retry_pending(root)
    assert not (root / "learner" / "pending.jsonl").exists()
    assert "gave up on record after 3 attempts" in (root / "learner" / "tutor.log").read_text()


def test_bad_items_are_skipped_not_fatal(learner_repo, tutor_tool, learner_tool):
    root = learner_repo
    learner_tool.onboard(PROFILE, root=root)
    tutor_tool.record({"subject": "class-9-science-exploration", "module": "chapter-01", "mystery": 1,
                       "steps": [{"step_ref": "b1-s1", "type": "learn", "outcome": "maybe"},
                                 {"step_ref": "b1-s2", "type": "choice", "outcome": "correct"},
                                 {"type": "choice"}]}, root=root)
    log = (root / "learner" / "tutor.log").read_text()
    assert "ignored unknown keys ['mystery']" in log and log.count("skipped steps") == 2
    session = next((root / "learner" / "sessions").glob("*.jsonl"))
    assert sum('"step"' in line for line in session.read_text().splitlines()) == 1
    assert not (root / "learner" / "pending.jsonl").exists()  # bad input is never retried


def test_bad_json_is_silent(run_tool, tutor_root):
    assert_silent(run_tool("tutor", "record", "--json", "{not json"))
    assert "not valid JSON" in (tutor_root / "learner" / "tutor.log").read_text()


def test_hooks_do_nothing_in_a_developer_checkout(learner_repo, run_tool):
    """No learner profile = the owner or a developer: never commit their work."""
    (learner_repo / "core" / "subjects" / "draft.txt").write_text("work in progress\n")
    assert_silent(hook(run_tool, learner_repo, "session-end", {"reason": "other"}))
    assert git(learner_repo, "log", "--format=%s", "-1").strip() == "clone"
    assert not (learner_repo / "learner").exists()


def test_end_without_git_identity_still_commits(learner_repo, tutor_tool, learner_tool, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    learner_tool.onboard(PROFILE, root=learner_repo)
    (learner_repo / "my-work" / "x.py").write_text("print(1)\n")
    tutor_tool.finish(learner_repo)
    author = git(learner_repo, "log", "-1", "--format=%an <%ae>").strip()
    assert author == "tutor <tutor@invalid>"
