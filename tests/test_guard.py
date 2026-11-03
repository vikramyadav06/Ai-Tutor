"""Item 4 of the owner's review: chained, piped or substituted commands after an allowed
`python tools/...` call must never run without a prompt.

Claude Code's own matcher (per its permissions docs) already refuses to approve
`allowed && other` with an allow rule, but auto-approves chained parts it thinks are
read-only, and doesn't document `$( )` inside an allowed command. tools/guard.py, a
PreToolUse hook, answers "ask" for all of these, which forces a prompt even when an allow
rule matches. Claude Code's matcher itself can't be run in a test; this tests the guard."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import guard  # noqa: E402
PAYLOAD = """'{"subject": "x", "notes_extra": "it\\u0027s fine; (really) | ok $(not run) `nope` && <b>"}'"""


@pytest.mark.parametrize("command", [
    "python tools/tutor.py record --json " + PAYLOAD,
    "python3 tools/learner.py show",
    "python tools/learner.py plan class-9-science --answers '{\"goal\": \"exam\"}'",
    "python tools/validate.py core/subjects/class-9-science/matter/lesson.json",
    "python tools/log_session.py summary --last 5",
    "python tools/tutor.py context",
])
def test_plain_calls_pass_through(command):
    assert guard.decide(command) is None


@pytest.mark.parametrize("command", [
    "python tools/learner.py show && rm -rf my-work",
    "python tools/learner.py show || curl https://evil.example",
    "python tools/learner.py show; ls -la",
    "python tools/learner.py show & cat .tutor/identity.json",
    "python tools/learner.py show | sh",
    "python tools/learner.py show |& tee out.txt",
    "python tools/learner.py show > /tmp/profile.txt",
    "python tools/learner.py show < /etc/passwd",
    "python tools/tutor.py record --json \"$(cat ~/.ssh/id_rsa)\"",
    "python tools/tutor.py record --json $(cat .tutor/identity.json)",
    "python tools/tutor.py record --json \"`whoami`\"",
    "python tools/tutor.py record --json `whoami`",
    "python tools/tutor.py record --json \"$HOME\"",
    "python tools/tutor.py record --json ${HOME}",
    "python tools/learner.py show\nrm -rf my-work",
    "python tools/learner.py show \\\n && rm x",
    "(python tools/learner.py show)",
    "ls; python tools/learner.py show",
    "cd /tmp && python tools/learner.py show",
    "FOO=1 python tools/learner.py show",
    "bash -c 'python tools/learner.py show'",
    "sh -c \"python3 tools/tutor.py context\"",
    "python /tmp/tools/tutor.py context",
    "python tools/tutor.py record --json '{\"a\": 1}",
    "python -c 'import os' tools/tutor.py",
])
def test_compound_or_odd_calls_must_prompt(command):
    assert guard.decide(command), command


def test_other_commands_are_left_to_claude_code():
    assert guard.decide("ls -la") is None
    assert guard.decide("pytest my-work/setup -v && rm -rf x") is None  # not ours; Claude Code's rules apply


def run_hook(event):
    return subprocess.run([sys.executable, str(REPO / "tools" / "guard.py")], input=json.dumps(event),
                          capture_output=True, text=True)


def test_hook_answers_ask():
    out = run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                    "tool_input": {"command": "python tools/learner.py show && rm -rf my-work"}})
    decision = json.loads(out.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse" and decision["permissionDecision"] == "ask"
    assert out.returncode == 0 and out.stderr == ""


def test_hook_is_silent_for_plain_calls_and_other_tools():
    for event in ({"tool_name": "Bash", "tool_input": {"command": "python tools/tutor.py context"}},
                  {"tool_name": "Read", "tool_input": {"file_path": "x"}}, {}):
        out = run_hook(event)
        assert out.returncode == 0 and out.stdout == "" and out.stderr == ""


def test_guard_is_registered_for_bash():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    entry = settings["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash" and "tools/guard.py" in entry["hooks"][0]["command"]
