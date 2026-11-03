"""Phase 2.5: multi-device sync. Two simulated devices share one bare repo standing in for the
learner's fork. Learning on A, then B, then A again loses nothing; a wrong code fails safely; a
tampered archive is rejected; nothing on the public branch is readable."""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from nacl.exceptions import CryptoError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import learner  # noqa: E402
import publish  # noqa: E402
import sync  # noqa: E402
import tutor  # noqa: E402

SUBJECT = "class-9-science-exploration"
ADULT = {"name": "Meera Iyer", "age_band": "25-34", "level": "professional", "explain_language": "en",
         "goals": ["Help my child with Class 9 science"], "preferred_styles": ["examples"], "pace": "steady"}
STUDENT = {"name": "Pinky", "age_band": "13-17", "level": "secondary", "explain_language": "en",
           "preferred_styles": ["visual"]}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def fork(tutor_root, tmp_path):
    """Device A (tutor_root) and the learner's fork (a bare repo)."""
    bare = tmp_path / "fork.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(tutor_root, "init", "-q", "-b", "main")
    (tutor_root / ".gitignore").write_text("learner/\n.tutor/\n")
    (tutor_root / "my-work").mkdir()
    (tutor_root / "my-work" / "README.md").write_text("your code\n")
    git(tutor_root, "add", "-A")
    git(tutor_root, "-c", "user.name=x", "-c", "user.email=x@invalid", "commit", "-q", "-m", "course")
    git(tutor_root, "remote", "add", "origin", str(bare))
    git(tutor_root, "push", "-q", "origin", "main")
    return bare


def new_device(fork, tmp_path, name):
    """A fresh clone of the learner's fork on another computer."""
    path = tmp_path / name
    git(tmp_path, "clone", "-q", str(fork), str(path))
    return path


def files(root, top):
    base = Path(root) / top
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()} if base.exists() else {}


def session(root, module, batch, extra, **more):
    """One teaching session as the hooks and the tutor's record calls run it."""
    tutor.session_start({"source": "startup"}, root)
    payload = {"subject": SUBJECT, "module": module, "agent": "claude-code",
               "steps": [{"step_ref": f"b{batch}-s1", "type": "learn", "outcome": "viewed"},
                         {"step_ref": f"b{batch}-s2", "type": "choice", "outcome": "correct"}],
               "batch_done": batch, "notes_extra": extra, **more}
    tutor.record(payload, root=root)
    tutor.finish(root)


def chapter_02_lesson(root):
    """A lesson the tutor wrote on this device."""
    lesson = json.loads((root / "core" / "subjects" / SUBJECT / "chapter-01" / "lesson.json").read_text())
    lesson.update(id="chapter-02", title="Chapter 2 (placeholder title)")
    folder = root / "core" / "subjects" / SUBJECT / "chapter-02"
    folder.mkdir()
    (folder / "lesson.json").write_text(json.dumps(lesson, indent=2))


# ---------- the main scenario ----------

def test_a_then_b_then_a_loses_nothing(tutor_root, fork, tmp_path):
    a = tutor_root
    learner.onboard(ADULT, root=a)
    learner.plan_subject(SUBJECT, {"goal": "exam"}, root=a)
    code, _ = learner.any_code(a)
    (a / "my-work" / "chapter-01").mkdir()
    (a / "my-work" / "chapter-01" / "observations.md").write_text("Ice stayed at 0 C while melting\n")
    chapter_02_lesson(a)
    session(a, "chapter-01", 1, "A: air is matter",
            private_terms=["Sunrise School"], model={"add": {"weak_areas": ["particles"]}},
            progress_entry="### 2026-11-03 – Chapter 1\n- Learned on device A")
    assert "refs/heads/tutor-sync" in git(fork, "for-each-ref", "--format=%(refname)")

    # device B: the learner enters their code; everything comes over
    b = new_device(fork, tmp_path, "device-b")
    assert learner.restore(code, root=b).startswith("merged:")
    profile_a = json.loads((a / "learner" / "profile.json").read_text())
    profile_b = json.loads((b / "learner" / "profile.json").read_text())
    assert profile_b == {**profile_a, "code_shown": True}  # B only adds: they already have the code
    for rel in ("learner/model.json", "learner/private_terms.json",
                f"learner/subjects/{SUBJECT}/plan.json", f"learner/subjects/{SUBJECT}/notes.md",
                f"learner/subjects/{SUBJECT}/progress.md", "my-work/chapter-01/observations.md",
                f"core/subjects/{SUBJECT}/chapter-02/lesson.json"):
        assert (b / rel).read_bytes() == (a / rel).read_bytes(), rel
    assert files(b, "learner/sessions") == {k: v for k, v in files(a, "learner/sessions").items()}
    assert "Chapter 2" in learner.summary(root=b) or "chapter-01" in learner.summary(root=b)

    # B learns
    (b / "my-work" / "chapter-02").mkdir(parents=True)
    (b / "my-work" / "chapter-02" / "answers.md").write_text("Sound needs a medium\n")
    session(b, "chapter-01", 2, "B: states of matter", module_done=True,
            private_terms=["Kumar Tuition"], model={"add": {"strengths": ["particles"]}},
            progress_entry="### 2026-11-04 – Chapter 1\n- Finished on device B")

    # back on A: the session start pulls B's work in
    session(a, "chapter-02", 1, "A again: a new chapter",
            progress_entry="### 2026-11-05 – Chapter 2\n- Started on device A")

    # A has everything from both devices
    sessions_a = files(a, "learner/sessions")
    assert len([k for k in sessions_a if k.endswith(".jsonl")]) == 3
    notes = (a / "learner" / "subjects" / SUBJECT / "notes.md").read_text()
    for line in ("A: air is matter", "B: states of matter", "A again: a new chapter"):
        assert line in notes
    progress = (a / "learner" / "subjects" / SUBJECT / "progress.md").read_text()
    assert progress.index("2026-11-05") < progress.index("2026-11-04") < progress.index("2026-11-03")
    terms = json.loads((a / "learner" / "private_terms.json").read_text())["terms"]
    assert "Sunrise School" in terms and "Kumar Tuition" in terms
    plan = json.loads((a / "learner" / "subjects" / SUBJECT / "plan.json").read_text())
    status = {m["id"]: m["status"] for m in plan["modules"]}
    assert status["chapter-01"] == "done" and status["chapter-02"] == "in-progress"
    assert (a / "my-work" / "chapter-02" / "answers.md").read_text() == "Sound needs a medium\n"
    model = json.loads((a / "learner" / "model.json").read_text())
    assert model["strengths"] == ["particles"]  # B's newer model won ...
    history = list((a / "learner" / "history").rglob("model.json"))
    assert history and any("particles" in json.loads(h.read_text())["weak_areas"] for h in history)  # ... A's is kept

    # and B gets session 3 next time, with nothing of its own lost
    tutor.session_start({"source": "startup"}, b)
    assert len([k for k in files(b, "learner/sessions") if k.endswith(".jsonl")]) == 3
    for rel, data in files(a, "learner/sessions").items():
        lines_b = set((b / rel).read_text().splitlines())
        assert set(data.decode().splitlines()) <= lines_b


def test_student_sync_code(tutor_root, fork, tmp_path):
    learner.onboard(STUDENT, root=tutor_root)
    learner.plan_subject(SUBJECT, {"goal": "exam"}, root=tutor_root)
    code, warning = learner.any_code(tutor_root)
    assert re.fullmatch(r"sync-[A-Z2-7]{52}", code) and "never sent anywhere" in warning
    assert not (tutor_root / ".tutor" / "identity.json").exists()
    session(tutor_root, "chapter-01", 1, "student notes")
    b = new_device(fork, tmp_path, "student-b")
    assert learner.restore(code.lower(), root=b).startswith("merged:")  # case doesn't matter
    assert json.loads((b / "learner" / "profile.json").read_text())["mode"] == "student"
    assert not (b / ".tutor" / "identity.json").exists()


# ---------- failing safely ----------

def test_wrong_code_changes_nothing(tutor_root, fork, tmp_path):
    learner.onboard(ADULT, root=tutor_root)
    real, _ = learner.any_code(tutor_root)
    session(tutor_root, "chapter-01", 1, "x")
    b = new_device(fork, tmp_path, "device-b")
    wrong = "lrn-abcd2345." + base64.b32encode(os.urandom(32)).decode().rstrip("=")
    with pytest.raises(learner.TutorError, match="doesn't match any saved progress"):
        learner.restore(wrong, root=b)
    assert not (b / "learner" / "profile.json").exists()  # only a line in tutor.log, nothing restored
    assert not (b / ".tutor" / "identity.json").exists()
    assert not (b / ".tutor" / "sync_state.json").exists()  # nothing marked rejected
    with pytest.raises(learner.TutorError, match="doesn't look like a code"):
        learner.restore("hello there", root=b)
    assert learner.restore(real, root=b).startswith("merged:")  # the right code still works


def test_no_saved_progress_yet(tutor_root, fork, tmp_path):
    learner.onboard(ADULT, root=tutor_root)
    code, _ = learner.any_code(tutor_root)
    b = new_device(fork, tmp_path, "device-b")
    with pytest.raises(learner.TutorError, match="no saved progress"):
        learner.restore(code, root=b)
    assert not (b / ".tutor" / "identity.json").exists()


def test_tampered_archive_is_rejected(tutor_root, fork, tmp_path):
    learner.onboard(ADULT, root=tutor_root)
    code, _ = learner.any_code(tutor_root)
    session(tutor_root, "chapter-01", 1, "real notes")
    # an attacker with push access adds a modified copy of the archive
    real = git(fork, "ls-tree", "-r", "--name-only", "tutor-sync").split()
    name = sorted(real)[-1]
    blob = bytearray(subprocess.run(["git", "cat-file", "blob", f"tutor-sync:{name}"], cwd=fork,
                                    capture_output=True, check=True).stdout)
    blob[-5] ^= 0x01
    with pytest.raises(CryptoError):
        sync.open_archive(bytes(blob), tutor_root)
    attacker = new_device(fork, tmp_path, "attacker")
    git(attacker, "fetch", "-q", "origin", "tutor-sync:tutor-sync")
    git(attacker, "switch", "-q", "tutor-sync")
    bad = Path(attacker) / "2026-11-03" / ("f" * 32 + ".bin")
    bad.parent.mkdir(exist_ok=True)
    bad.write_bytes(bytes(blob))
    git(attacker, "add", "-A")
    git(attacker, "-c", "user.name=x", "-c", "user.email=x@invalid", "commit", "-q", "-m", "x")
    git(attacker, "push", "-q", "origin", "tutor-sync")
    b = new_device(fork, tmp_path, "device-b")
    assert learner.restore(code, root=b) == f"merged:{len(real)}"  # the real archives only
    state = json.loads((b / ".tutor" / "sync_state.json").read_text())
    assert state["rejected"] == ["2026-11-03/" + "f" * 32 + ".bin"]
    assert "rejected archive" in (b / "learner" / "tutor.log").read_text()


def test_unsafe_paths_in_an_archive_are_ignored(tutor_root):
    learner.onboard(ADULT, root=tutor_root)
    payload = {"format": 1, "files": {"../../evil.sh": base64.b64encode(b"x").decode(),
                                      "/etc/x": base64.b64encode(b"x").decode(),
                                      ".tutor/identity.json": base64.b64encode(b"x").decode(),
                                      "tools/tutor.py": base64.b64encode(b"x").decode(),
                                      "learner/ok.txt": base64.b64encode(b"fine").decode()}, "mtimes": {}}
    assert sync.merge_archive(tutor_root, payload) == ["learner/ok.txt"]
    assert not (tutor_root.parent / "evil.sh").exists()


# ---------- the public branch ----------

def test_nothing_readable_on_the_public_branch(tutor_root, fork):
    learner.onboard(ADULT, root=tutor_root)
    code, _ = learner.any_code(tutor_root)
    session(tutor_root, "chapter-01", 1, "Meera's private revision line", private_terms=["Sunrise School"])
    names = git(fork, "ls-tree", "-r", "--name-only", "tutor-sync").split()
    assert names and all(sync.ARCHIVE_PATH.match(n) for n in names)
    identity = json.loads((tutor_root / ".tutor" / "identity.json").read_text())
    for name in names:
        blob = subprocess.run(["git", "cat-file", "blob", f"tutor-sync:{name}"], cwd=fork,
                              capture_output=True, check=True).stdout
        for secret in (b"Meera", b"Sunrise", b"revision", b"learner/", b"profile", b"chapter-01",
                       identity["learner_id"].encode(), identity["signing_seed_b64"].encode(), code.encode()):
            assert secret not in blob
    meta = git(fork, "log", "--format=%an|%ae|%aI|%cI|%s", "tutor-sync").splitlines()
    for line in meta:
        an, ae, ad, cd, subject = line.split("|")
        assert (an, ae, subject) == ("tutor", "tutor@invalid", "sync")
        assert ad.endswith("T00:00:00Z") or "T00:00:00" in ad
        assert "T00:00:00" in cd
    assert subprocess.run(["git", "merge-base", "main", "tutor-sync"], cwd=fork, capture_output=True).returncode != 0
    assert git(fork, "for-each-ref", "--format=%(refname)", "refs/heads/tutor-data") == ""  # sync never touches it


def test_archive_never_holds_device_secrets_or_the_outbox(tutor_root, fork):
    learner.onboard(ADULT, root=tutor_root)
    (tutor_root / ".tutor" / "outbox" / "k1" / "2026-11-03").mkdir(parents=True)
    (tutor_root / ".tutor" / "outbox" / "k1" / "2026-11-03" / ("a" * 32 + ".bin")).write_bytes(b"queued")
    (tutor_root / "learner" / "tutor.log").write_text("local only\n")
    blob, _ = sync.build_archive(tutor_root)
    payload = sync.open_archive(blob, tutor_root)
    assert all(sync.safe_rel(rel) for rel in payload["files"])
    assert not any(rel.startswith(".tutor") for rel in payload["files"])
    assert "learner/tutor.log" not in payload["files"]
    raw = json.dumps(payload)
    seed = json.loads((tutor_root / ".tutor" / "identity.json").read_text())["signing_seed_b64"]
    assert seed not in raw and "queued" not in raw


def test_push_is_skipped_when_nothing_changed(tutor_root, fork):
    learner.onboard(ADULT, root=tutor_root)
    assert sync.push(tutor_root) == "pushed"
    assert sync.push(tutor_root) == "unchanged"
    learner.update_model(adds=[("weak_areas", "sound")], root=tutor_root)
    assert sync.push(tutor_root) == "pushed"


def test_sync_off_does_nothing(tutor_root, fork):
    learner.onboard(ADULT, root=tutor_root)
    learner.set_profile_flag("sync", False, tutor_root)
    assert sync.push(tutor_root) == "off" and sync.pull(tutor_root) == "off"
    assert git(fork, "for-each-ref", "--format=%(refname)", "refs/heads/tutor-sync") == ""


def test_hooks_stay_silent_with_sync(tutor_root, fork):
    env = {**os.environ, "TUTOR_ROOT": str(tutor_root)}
    learner.onboard(ADULT, root=tutor_root)
    for event, stdin in (("session-end", {"reason": "other"}),):
        out = subprocess.run([sys.executable, str(REPO / "tools" / "tutor.py"), "hook", event],
                             input=json.dumps(stdin), capture_output=True, text=True, env=env, cwd=tutor_root)
        assert out.returncode == 0 and out.stdout == "" and out.stderr == ""
    assert "refs/heads/tutor-sync" in git(fork, "for-each-ref", "--format=%(refname)")
    assert not (tutor_root / "learner" / "tutor.log").exists()


# ---------- keys ----------

def test_sync_key_is_derived_not_the_seed():
    seed = os.urandom(32)
    key = sync.derive_key(seed)
    assert len(key) == 32 and key != seed
    assert key == sync.derive_key(seed) and key != sync.derive_key(os.urandom(32))
    from nacl.encoding import RawEncoder
    from nacl.hash import blake2b
    assert key != blake2b(b"", digest_size=32, key=seed, person=b"other-context", encoder=RawEncoder)


# ---------- merge rules ----------

def test_jsonl_logs_are_combined_in_time_order():
    a = b'{"t": "2026-11-03T10:00Z", "event": "start"}\n{"t": "2026-11-03T10:05Z", "event": "step"}\n'
    b = b'{"t": "2026-11-03T10:00Z", "event": "start"}\n{"t": "2026-11-03T10:03Z", "event": "move"}\n'
    lines = sync._merge_jsonl(a, b).decode().splitlines()
    assert [json.loads(x)["event"] for x in lines] == ["start", "move", "step"]


def test_newest_wins_and_the_other_copy_is_kept(tutor_root):
    (tutor_root / "learner").mkdir()
    f = tutor_root / "learner" / "model.json"
    f.write_text('{"pace": "slow"}')
    os.utime(f, (1000, 1000))
    assert sync.merge_file(tutor_root, "learner/model.json", b'{"pace": "fast"}', 2000, "s1")
    assert f.read_text() == '{"pace": "fast"}'
    assert (tutor_root / "learner" / "history" / "s1-replaced" / "learner" / "model.json").read_text() == '{"pace": "slow"}'
    # an older remote copy doesn't win, but is kept too
    assert not sync.merge_file(tutor_root, "learner/model.json", b'{"pace": "steady"}', 500, "s2")
    assert f.read_text() == '{"pace": "fast"}'
    assert "steady" in (tutor_root / "learner" / "history" / "s2-other-device" / "learner" / "model.json").read_text()


def test_ingest_side_can_never_mistake_sync_for_data():
    """Repo B's ingest is built in Phase 3; TECH_SPEC requires it to fetch only tutor-data and
    to test that it ignores tutor-sync. Here: the two branches can't be confused."""
    spec = (REPO / "docs" / "TECH_SPEC.md").read_text()
    assert "never fetch `tutor-sync`" in spec and "ingest ignores `tutor-sync`" in spec
    assert sync.BRANCH != publish.BRANCH
    data_path = re.compile(r"^k\d+/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.bin$")  # TECH_SPEC §10 step 4
    assert not data_path.match("2026-11-03/" + "a" * 32 + ".bin")
    assert not sync.ARCHIVE_PATH.match("k1/2026-11-03/" + "a" * 32 + ".bin")


def test_progress_and_notes_keep_every_section_and_their_header():
    head = "# Progress: X\n\n## Session history\n<!-- newest first -->\n"
    a = (head + "### 2026-11-05 – A\n- on A\n### 2026-11-03 – first\n- shared\n").encode()
    b = (head + "### 2026-11-04 – B\n- on B\n### 2026-11-03 – first\n- shared\n").encode()
    merged = sync._merge_sections(a, b, newest_first=True).decode()
    assert merged.startswith(head)
    assert merged.index("2026-11-05") < merged.index("2026-11-04") < merged.index("2026-11-03")
    assert merged.count("### 2026-11-03") == 1
    assert sync._merge_sections(a, (head + "### 2026-11-03 – first\n- shared\n").encode(), True) == a
    notes_a = b"# Revision notes: x\n\n## Ch 1 - one\n_2026-11-03_\n\n- p\n\n"
    notes_b = b"# Revision notes: x\n\n## Ch 1 - one\n_2026-11-03_\n\n- p\n\n## Ch 1 - two\n_2026-11-04_\n\n- q\n\n"
    merged = sync._merge_sections(notes_a, notes_b, newest_first=False).decode()
    assert merged.startswith("# Revision notes: x\n\n## Ch 1 - one") and merged.index("one") < merged.index("two")


def test_plan_keeps_the_furthest_status():
    newer = json.dumps({"modules": [{"id": "a", "status": "in-progress"}, {"id": "b", "status": "not-started"}]})
    older = json.dumps({"modules": [{"id": "a", "status": "done"}, {"id": "c", "status": "done"}]})
    merged = json.loads(sync._merge_plan(newer.encode(), older.encode()))
    assert [m["status"] for m in merged["modules"]] == ["done", "not-started"]


def test_restore_asks_for_packages_first(tutor_root, monkeypatch):
    monkeypatch.setattr(learner, "missing_packages", lambda: ["pynacl"])
    with pytest.raises(learner.TutorError, match="needs packages pynacl"):
        learner.restore("lrn-abcd2345." + base64.b32encode(os.urandom(32)).decode().rstrip("="), root=tutor_root)
    assert not (tutor_root / ".tutor" / "identity.json").exists()


def test_restore_outside_a_git_clone(tutor_root):
    with pytest.raises(learner.TutorError, match="isn't a git clone"):
        learner.restore("sync-" + base64.b32encode(os.urandom(32)).decode().rstrip("="), root=tutor_root)
    assert not (tutor_root / ".tutor" / "sync.json").exists()
