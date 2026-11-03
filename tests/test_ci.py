"""TECH_SPEC §11: read-only workflows, no secrets, no pull_request_target, pinned actions."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.yml"))


def test_there_is_a_checks_workflow():
    assert (REPO / ".github" / "workflows" / "checks.yml") in WORKFLOWS


def test_workflows_are_read_only_and_safe():
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in text.splitlines())
        assert re.search(r"^permissions:\s*\n\s+contents:\s*read\s*$", code, re.M), wf.name
        assert "pull_request_target" not in code and "workflow_run" not in code, wf.name
        assert "secrets." not in code, wf.name
        assert not re.search(r":\s*write\b", code), f"{wf.name} asks for write access"


def test_actions_are_pinned_to_full_shas():
    for wf in WORKFLOWS:
        for line in wf.read_text(encoding="utf-8").splitlines():
            m = re.search(r"uses:\s*(\S+)", line)
            if m:
                assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", m.group(1)), line
                assert re.search(r"# v\d+\.\d+\.\d+", line), f"tag comment missing: {line}"


def test_dependabot_watches_actions():
    text = (REPO / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: github-actions" in text
