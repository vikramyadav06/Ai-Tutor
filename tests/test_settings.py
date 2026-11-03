"""Claude Code settings: hooks run the bookkeeping; the allow-list is exactly the tutor's own
scripts (plus writing lessons), so the learner never sees a prompt for bookkeeping."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
SCRIPTS = ("tutor", "learner", "log_session", "validate")


def test_allow_list_is_exactly_the_tutor_scripts():
    expected = {f"Bash({py} tools/{s}.py *)" for s in SCRIPTS for py in ("python", "python3")}
    expected.add("Edit(/core/subjects/**)")
    assert set(SETTINGS["permissions"]["allow"]) == expected


def test_allow_list_has_no_general_access():
    for rule in SETTINGS["permissions"]["allow"]:
        assert rule not in ("Bash", "Bash(*)", "Edit", "Write", "WebFetch", "WebSearch")
        for risky in ("rm", "curl", "wget", "git push", "sh ", "bash", "WebFetch", "Read(", "(/learner", ".tutor"):
            assert risky not in rule, rule


def test_private_folders_are_protected():
    deny = set(SETTINGS["permissions"]["deny"])
    assert {"Read(/.tutor/**)", "Edit(/.tutor/**)", "Edit(/learner/**)", "Bash(curl *)", "Bash(wget *)"} <= deny


def test_hooks_run_the_tutor_tool():
    hooks = SETTINGS["hooks"]
    start = hooks["SessionStart"][0]
    assert set(start["matcher"].split("|")) == {"startup", "resume", "clear", "compact"}
    assert "tools/tutor.py\" hook session-start" in start["hooks"][0]["command"]
    end = hooks["SessionEnd"][0]
    assert "tools/tutor.py\" hook session-end" in end["hooks"][0]["command"]
    assert end["hooks"][0]["timeout"] <= 60  # SessionEnd budget is capped at 60 s
    for entry in (start, end):
        assert "$CLAUDE_PROJECT_DIR" in entry["hooks"][0]["command"]
        assert "2>/dev/null" in entry["hooks"][0]["command"]


def test_agents_md_keeps_the_learner_in_a_tutoring_conversation():
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "only ever experiences a tutor" in text
    assert "never between steps" in text
    for allowed in ("consent question", "learner code", "gh auth login"):
        assert allowed in text
    # the old instructions that told the tutor to announce bookkeeping are gone
    for banned in ("one short line", "mention it in", "log_session.py step", "tools/learner.py add-term"):
        assert banned not in text, banned


def test_agents_md_review_rules():
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    for needle in ("no emojis", "one batch at a time", "chapter list from them", "never from memory",
                   "provisional", "never invent marks", "unreviewed", "Never guess"):
        assert needle in text, needle


def test_agents_md_consent_rules():
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    for needle in ("student mode", "adult mode", "never ask and never mention sharing",
                   "show the learner code once", "delete my data"):
        assert needle.lower() in text.lower(), needle
