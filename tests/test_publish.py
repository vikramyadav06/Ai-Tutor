"""TECH_SPEC §14 Phase 2: publish.py against a local bare repo produces an orphan branch with
only .bin files, a neutral author, day-rounded dates, and never pushes main."""
import base64
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from nacl.public import PrivateKey

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import learner  # noqa: E402
import publish  # noqa: E402
import tutor  # noqa: E402

CONFIG = {"enabled": True, "data_branch": "tutor-data", "max_record_bytes": 262144, "student_collection": False,
          "keys": [{"key_id": "k1", "public_key_b64": base64.b64encode(bytes(PrivateKey.generate().public_key)).decode(),
                    "status": "active"}]}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def fork(tutor_root, tmp_path):
    """The learner's clone (tutor_root) with origin = a local bare repo standing in for their fork."""
    bare = tmp_path / "fork.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(tutor_root, "init", "-q", "-b", "main")
    (tutor_root / ".gitignore").write_text("learner/\n.tutor/\n")
    git(tutor_root, "add", "-A")
    git(tutor_root, "-c", "user.name=Learner Name", "-c", "user.email=learner@example.com",
        "commit", "-q", "-m", "course")
    git(tutor_root, "remote", "add", "origin", str(bare))
    git(tutor_root, "push", "-q", "origin", "main")
    return bare


def add_outbox(root, n=2, day="2026-11-03"):
    out = root / ".tutor" / "outbox" / "k1" / day
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for _ in range(n):
        name = uuid.uuid4().hex
        (out / f"{name}.bin").write_bytes(os.urandom(64))
        names.append(f"k1/{day}/{name}.bin")
    return names


def test_publish_makes_an_orphan_data_branch(tutor_root, fork):
    main_before = git(fork, "rev-parse", "refs/heads/main")
    head_before = git(tutor_root, "rev-parse", "HEAD")
    names = add_outbox(tutor_root, 2)
    assert publish.publish(tutor_root, CONFIG, day="2026-11-03") == "pushed:2"

    # only main (untouched) and tutor-data exist on the remote
    refs = git(fork, "for-each-ref", "--format=%(refname)").split()
    assert sorted(refs) == ["refs/heads/main", "refs/heads/tutor-data"]
    assert git(fork, "rev-parse", "refs/heads/main") == main_before
    # orphan: no history shared with main
    result = subprocess.run(["git", "merge-base", "main", "tutor-data"], cwd=fork, capture_output=True)
    assert result.returncode != 0
    assert git(fork, "rev-list", "--count", "tutor-data") == "1"
    # only the encrypted files
    files = git(fork, "ls-tree", "-r", "--name-only", "tutor-data").split()
    assert sorted(files) == sorted(names)
    assert all(re.fullmatch(r"k\d+/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.bin", f) for f in files)
    # neutral identity, day-rounded dates
    meta = git(fork, "log", "-1", "--format=%an|%ae|%cn|%ce|%aI|%cI|%s", "tutor-data").split("|")
    assert meta[:4] == ["tutor", "tutor@invalid", "tutor", "tutor@invalid"]
    assert meta[4].startswith("2026-11-03T00:00:00") and meta[5].startswith("2026-11-03T00:00:00")
    assert meta[6] == "data"
    # the learner's own checkout is untouched and the outbox is empty
    assert git(tutor_root, "rev-parse", "HEAD") == head_before
    assert git(tutor_root, "symbolic-ref", "--short", "HEAD") == "main"
    assert git(tutor_root, "status", "--porcelain") == ""
    assert not list((tutor_root / ".tutor" / "outbox").rglob("*.bin"))


def test_second_publish_appends(tutor_root, fork):
    add_outbox(tutor_root, 1)
    publish.publish(tutor_root, CONFIG, day="2026-11-03")
    add_outbox(tutor_root, 1, day="2026-11-04")
    assert publish.publish(tutor_root, CONFIG, day="2026-11-04") == "pushed:1"
    assert git(fork, "rev-list", "--count", "tutor-data") == "2"
    assert len(git(fork, "ls-tree", "-r", "--name-only", "tutor-data").split()) == 2


def test_another_device_pushed_first(tutor_root, fork, tmp_path):
    add_outbox(tutor_root, 1)
    publish.publish(tutor_root, CONFIG, day="2026-11-03")
    # the same learner's other device pushes to the same fork
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(fork), str(other))
    git(other, "fetch", "-q", "origin", "tutor-data:tutor-data")
    git(other, "switch", "-q", "tutor-data")
    (other / "k1" / "2026-11-04").mkdir(parents=True)
    (other / "k1" / "2026-11-04" / f"{uuid.uuid4().hex}.bin").write_bytes(b"x")
    git(other, "add", "-A")
    git(other, "-c", "user.name=tutor", "-c", "user.email=tutor@invalid", "commit", "-q", "-m", "data")
    git(other, "push", "-q", "origin", "tutor-data")
    add_outbox(tutor_root, 1, day="2026-11-04")
    assert publish.publish(tutor_root, CONFIG, day="2026-11-04") == "pushed:1"
    assert len(git(fork, "ls-tree", "-r", "--name-only", "tutor-data").split()) == 3


def test_disabled_or_empty_does_nothing(tutor_root, fork):
    add_outbox(tutor_root, 1)
    assert publish.publish(tutor_root, {**CONFIG, "enabled": False}) == "disabled"
    assert git(fork, "for-each-ref", "--format=%(refname)") == "refs/heads/main"
    for f in (tutor_root / ".tutor" / "outbox").rglob("*.bin"):
        f.unlink()
    assert publish.publish(tutor_root, CONFIG) == "nothing"


def test_odd_outbox_files_are_never_published(tutor_root, fork):
    add_outbox(tutor_root, 1)
    stray = tutor_root / ".tutor" / "outbox" / "k1" / "2026-11-03" / "notes.txt"
    stray.write_text("private")
    (tutor_root / ".tutor" / "outbox" / "profile.bin").write_bytes(b"x")
    publish.publish(tutor_root, CONFIG, day="2026-11-03")
    files = git(fork, "ls-tree", "-r", "--name-only", "tutor-data").split()
    assert len(files) == 1 and files[0].endswith(".bin") and "profile" not in files[0]


def fake_gh(tmp_path, authed, fork_target):
    """A stand-in for the GitHub CLI: `auth status` and `repo fork --remote`."""
    script = tmp_path / "gh"
    script.write_text(f"""#!/bin/sh
if [ "$1" = "auth" ]; then exit {0 if authed else 1}; fi
if [ "$1" = "repo" ] && [ "$2" = "fork" ]; then
  git remote rename origin upstream && git remote add origin "{fork_target}"
  exit $?
fi
exit 2
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_fork_from_upstream_with_gh(tutor_root, fork, tmp_path):
    git(tutor_root, "remote", "set-url", "origin", "https://github.com/vikramwebgarh/Ai-Tutor.git")
    add_outbox(tutor_root, 1)
    # gh signed out: keep the files, flag a one-time `gh auth login` request
    assert publish.publish(tutor_root, CONFIG, gh=fake_gh(tmp_path, False, fork)) == "needs-gh-auth"
    assert (tutor_root / ".tutor" / "needs_gh_auth").exists()
    assert len(list((tutor_root / ".tutor" / "outbox").rglob("*.bin"))) == 1
    # gh signed in: fork, then push to the fork only
    assert publish.publish(tutor_root, CONFIG, gh=fake_gh(tmp_path, True, fork)) == "pushed:1"
    assert git(tutor_root, "remote", "get-url", "upstream") == "https://github.com/vikramwebgarh/Ai-Tutor.git"
    assert not (tutor_root / ".tutor" / "needs_gh_auth").exists()
    assert "refs/heads/tutor-data" in git(fork, "for-each-ref", "--format=%(refname)")


def test_publish_source_never_pushes_another_branch():
    source = (REPO / "tools" / "publish.py").read_text()
    pushes = re.findall(r'git\(wt, "push"[^)]*\)', source)
    assert pushes and all("refspec" in p for p in pushes)
    assert 'refspec = f"refs/heads/{branch}:refs/heads/{branch}"' in source


def test_end_to_end_session_is_silent_and_shared(tutor_root, fork, tmp_path):
    """A whole adult session through the real hooks: nothing printed, data on tutor-data."""
    key = PrivateKey.generate()
    project = json.loads((tutor_root / "project.json").read_text())
    project["collector"].update(enabled=True, keys=[{"key_id": "k1", "status": "active",
                                                    "public_key_b64": base64.b64encode(bytes(key.public_key)).decode()}])
    (tutor_root / "project.json").write_text(json.dumps(project))
    env = {**os.environ, "TUTOR_ROOT": str(tutor_root)}

    def run(*args, stdin=""):
        return subprocess.run([sys.executable, *args], input=stdin, capture_output=True, text=True, env=env,
                              cwd=tutor_root)

    start = run(str(REPO / "tools" / "tutor.py"), "hook", "session-start", stdin='{"source": "startup"}')
    assert start.returncode == 0 and start.stderr == ""
    for args in (["learner.py", "onboard", "--answers", json.dumps(
                     {"age_band": "25-34", "level": "professional", "preferred_styles": ["examples"]})],
                 ["learner.py", "plan", "python", "--answers", "{}"],
                 ["tutor.py", "record", "--json", json.dumps({"sharing": True})],
                 ["tutor.py", "record", "--json", json.dumps(
                     {"subject": "python", "module": "first-steps", "agent": "claude-code",
                      "steps": [{"step_ref": "b1-s1", "type": "learn", "outcome": "viewed"}],
                      "batch_done": None, "end": True})]):
        result = run(str(REPO / "tools" / args[0]), *args[1:])
        assert result.returncode == 0 and result.stdout == "" and result.stderr == "", args
    end = run(str(REPO / "tools" / "tutor.py"), "hook", "session-end", stdin='{"reason": "other"}')
    assert end.returncode == 0 and end.stdout == "" and end.stderr == ""

    assert not (tutor_root / "learner" / "tutor.log").exists()
    files = git(fork, "ls-tree", "-r", "--name-only", "tutor-data").split()
    assert len(files) == 1
    from nacl.public import SealedBox
    blob = subprocess.run(["git", "cat-file", "blob", f"tutor-data:{files[0]}"], cwd=fork,
                          capture_output=True, check=True).stdout
    record = json.loads(SealedBox(key).decrypt(blob))["record"]
    assert record["schema"] == "session.adult.v1" and record["subject"] == "python"
    # the learner's next session is told to show the learner code once
    nxt = run(str(REPO / "tools" / "tutor.py"), "hook", "session-start", stdin='{"source": "startup"}')
    assert "the code moment" in json.loads(nxt.stdout)["hookSpecificOutput"]["additionalContext"]
