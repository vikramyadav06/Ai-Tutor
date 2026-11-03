"""Phase 2.5: reviewed lessons and tutor updates arrive automatically from upstream main.
An 'owner' repo pushes to a local bare repo standing in for vikramwebgarh/Ai-Tutor; a learner's
clone updates at session start."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import learner  # noqa: E402
import sync  # noqa: E402
import tutor  # noqa: E402
import update  # noqa: E402

SUBJECT = "class-9-science-exploration"
STUDENT = {"name": "Pinky", "age_band": "13-17", "level": "secondary", "preferred_styles": ["visual"]}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def commit(cwd, message):
    git(cwd, "add", "-A")
    git(cwd, "-c", "user.name=Owner", "-c", "user.email=owner@invalid", "commit", "-q", "-m", message)


@pytest.fixture
def course(tutor_root, tmp_path, monkeypatch):
    """(owner checkout, upstream bare repo, learner clone that has onboarded)."""
    owner = tutor_root
    (owner / ".gitignore").write_text("learner/\n.tutor/\n")
    (owner / "AGENTS.md").write_text("# AI Tutor\nversion 1\n")
    (owner / "my-work").mkdir()
    (owner / "my-work" / "README.md").write_text("your code\n")
    git(owner, "init", "-q", "-b", "main")
    commit(owner, "course v1")
    upstream = tmp_path / "upstream.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(upstream))
    git(owner, "remote", "add", "origin", str(upstream))
    git(owner, "push", "-q", "origin", "main")
    monkeypatch.setenv("TUTOR_UPSTREAM_URL", str(upstream))
    learner_root = tmp_path / "learner-clone"
    git(tmp_path, "clone", "-q", str(upstream), str(learner_root))
    learner.onboard(STUDENT, root=learner_root)
    learner.plan_subject(SUBJECT, {"goal": "exam"}, root=learner_root)
    return owner, upstream, learner_root


def owner_pushes(owner, message, changes):
    for rel, content in changes.items():
        path = owner / rel
        if content is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content, indent=2))
    commit(owner, message)
    git(owner, "push", "-q", "origin", "main")


def lesson(titles, status, planned=None, module="chapter-02"):
    base = json.loads((REPO / "tests" / "fixtures" / "subjects" / SUBJECT / "chapter-01" / "lesson.json").read_text())
    batch = base["batches"][0]
    out = {**base, "id": module, "title": "Chapter 2 (placeholder title)", "status": status,
           "batches": [{**batch, "title": t} for t in titles]}
    if planned:
        out["planned_batches"] = planned
    else:
        out.pop("planned_batches", None)
    return out


def test_fast_forward_when_nothing_local(course):
    owner, upstream, me = course
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n",
                                     f"core/subjects/{SUBJECT}/chapter-03/lesson.json":
                                     lesson(["One", "Two"], "reviewed", module="chapter-03")})
    assert update.update(me) == "fast-forward"
    assert git(me, "rev-parse", "HEAD") == git(upstream, "rev-parse", "main")
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"
    assert update.update(me) == "up-to-date"


def test_reviewed_lesson_arrives_mid_course_and_progress_carries_over(course):
    owner, upstream, me = course
    # the tutor wrote chapter 2 on the learner's machine and taught two of its three batches
    draft = lesson(["What matter is", "States of matter", "Changing state"], "unreviewed",
                   planned=["What matter is", "States of matter", "Changing state"])
    path = me / "core" / "subjects" / SUBJECT / "chapter-02" / "lesson.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(draft, indent=2))
    for n in (1, 2):
        tutor.record({"subject": SUBJECT, "module": "chapter-02", "batch_done": n}, root=me)
    tutor.finish(me)  # session end: the learner's own commit, so a plain fast-forward is impossible
    head_before = git(me, "rev-parse", "HEAD")

    # the reviewed version (restructured, four batches) is merged upstream
    reviewed = lesson(["What Matter Is", "States of matter!", "Particles in motion", "Practice"], "reviewed")
    owner_pushes(owner, "reviewed chapter 2", {f"core/subjects/{SUBJECT}/chapter-02/lesson.json": reviewed,
                                                "AGENTS.md": "# AI Tutor\nversion 2\n"})
    result = update.update(me)
    assert result.startswith("updated:")

    now = json.loads(path.read_text())
    assert now["status"] == "reviewed" and len(now["batches"]) == 4
    kept = list((me / "learner" / "history").rglob("chapter-02/lesson.json"))
    assert len(kept) == 1 and json.loads(kept[0].read_text())["status"] == "unreviewed"
    plan = json.loads((me / "learner" / "subjects" / SUBJECT / "plan.json").read_text())
    row = next(r for r in plan["modules"] if r["id"] == "chapter-02")
    assert row["batches_done"] == ["What Matter Is", "States of matter!"]  # not restarted
    assert row["batches_done_before_review"] == ["What matter is", "States of matter"]
    assert row["status"] == "in-progress"
    summary = learner.summary(root=me)
    assert 'next: Chapter 2 (placeholder title) (chapter-02, written, reviewed; resume at batch 3 of 4 ' \
           '"Particles in motion")' in summary, summary
    # history only grew: the learner's commits are still there
    assert git(me, "merge-base", "--is-ancestor", head_before, "HEAD") == ""
    assert git(me, "log", "-1", "--format=%s").startswith("tutor: course update to ")
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"
    # and the reviewed lesson is not proposed back to Repo B, nor replaced by a draft from sync
    import collect
    assert path not in collect.new_lessons(me)
    assert not sync.merge_file(me, f"core/subjects/{SUBJECT}/chapter-02/lesson.json",
                               json.dumps(draft).encode(), 4_000_000_000, "s1")
    assert json.loads(path.read_text())["status"] == "reviewed"


def test_map_batches_by_share_when_titles_differ():
    old = lesson(["A", "B", "C", "D"], "unreviewed")
    new = lesson(["One", "Two", "Three", "Four", "Five", "Six"], "reviewed")
    assert learner.map_batches(["A", "B"], old, new) == ["One", "Two", "Three"]  # half done stays half done
    assert learner.map_batches([], old, new) == []
    assert learner.map_batches(["A"], old, new) == ["One"]  # rounded down: nothing new skipped


def test_offline_start_works_and_retries(course, monkeypatch, tmp_path):
    owner, upstream, me = course
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n"})
    monkeypatch.setenv("TUTOR_UPSTREAM_URL", str(tmp_path / "offline.git"))
    env = {**os.environ, "TUTOR_ROOT": str(me)}
    out = subprocess.run([sys.executable, str(REPO / "tools" / "tutor.py"), "hook", "session-start"],
                         input='{"source": "startup"}', capture_output=True, text=True, env=env, cwd=me)
    assert out.returncode == 0 and out.stderr == ""
    assert "Pinky" in json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]  # teaching goes on
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 1\n"
    monkeypatch.setenv("TUTOR_UPSTREAM_URL", str(upstream))  # back online: next session catches up
    tutor.session_start({"source": "startup"}, me)
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"


def test_learner_files_and_work_are_never_overwritten(course):
    owner, upstream, me = course
    (me / "my-work" / "chapter-01").mkdir(parents=True)
    (me / "my-work" / "chapter-01" / "answers.md").write_text("my answers, not committed yet\n")
    (me / "my-work" / "README.md").write_text("my own notes on the readme\n")
    profile_before = (me / "learner" / "profile.json").read_text()
    notes = me / "learner" / "subjects" / SUBJECT / "notes.md"
    notes.write_text("my notes\n")
    # upstream (wrongly) carries files in the learner's own folders, and changes the course
    owner_pushes(owner, "bad commit", {"my-work/chapter-01/answers.md": "upstream answers\n",
                                       "my-work/README.md": "upstream readme\n",
                                       "learner/profile.json": "{}",
                                       "AGENTS.md": "# AI Tutor\nversion 2\n"})
    update.update(me)
    assert (me / "my-work" / "chapter-01" / "answers.md").read_text() == "my answers, not committed yet\n"
    assert (me / "my-work" / "README.md").read_text() == "my own notes on the readme\n"
    assert (me / "learner" / "profile.json").read_text() == profile_before
    assert notes.read_text() == "my notes\n"
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"


def test_a_course_file_changed_on_both_sides_is_kept_and_retried(course):
    owner, upstream, me = course
    (me / "AGENTS.md").write_text("# AI Tutor\nmy local edit\n")
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n",
                                     "core/allowed_hosts.txt": "example.com\n"})
    assert update.update(me) == "partial:1"
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nmy local edit\n"
    assert (me / "core" / "allowed_hosts.txt").read_text() == "example.com\n"
    assert "kept the local AGENTS.md" in (me / "learner" / "tutor.log").read_text()
    (me / "AGENTS.md").write_text("# AI Tutor\nversion 1\n")  # the edit is undone
    assert update.update(me).startswith("updated:")
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"


def test_files_removed_upstream_go_only_if_unchanged_here(course):
    owner, upstream, me = course
    owner_pushes(owner, "remove", {"core/allowed_hosts.txt": None})
    update.update(me)
    assert not (me / "core" / "allowed_hosts.txt").exists()


def test_never_updates_a_developer_checkout(course):
    owner, upstream, me = course
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n"})
    shutil.rmtree(me / "learner")
    assert update.update(me) == "not-a-learner-copy"
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 1\n"


def test_unusual_git_state_is_left_alone(course):
    owner, upstream, me = course
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n"})
    git(me, "checkout", "-q", "--detach")
    assert update.update(me) == "busy:detached HEAD"
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 1\n"


def test_reuse_a_reviewed_lesson_for_the_same_syllabus_and_chapter(course):
    owner, upstream, me = course
    # upstream has a reviewed subject built from the same book, under another id
    other = json.loads((me / "core" / "subjects" / SUBJECT / "catalog.json").read_text())
    other["subject"] = "cbse-science-9-exploration"
    owner_pushes(owner, "reviewed subject", {
        "core/subjects/cbse-science-9-exploration/catalog.json": other,
        "core/subjects/cbse-science-9-exploration/chapter-03/lesson.json":
            {**lesson(["One", "Two"], "reviewed", module="chapter-03"), "subject": "cbse-science-9-exploration"}})
    update.update(me)
    source = learner.reuse_lesson(SUBJECT, "chapter-03", root=me)
    assert source.name == "chapter-03" and source.parent.name == "cbse-science-9-exploration"
    reused = json.loads((me / "core" / "subjects" / SUBJECT / "chapter-03" / "lesson.json").read_text())
    assert reused["status"] == "reviewed" and reused["subject"] == SUBJECT and reused["id"] == "chapter-03"
    # no reviewed lesson for chapter 4, or for another edition: the tutor writes one
    assert learner.reuse_lesson(SUBJECT, "chapter-04", root=me) is None
    catalog_path = me / "core" / "subjects" / SUBJECT / "catalog.json"
    mine = json.loads(catalog_path.read_text())
    mine["syllabus"]["edition"] = "2027-28"
    catalog_path.write_text(json.dumps(mine))
    shutil.rmtree(me / "core" / "subjects" / SUBJECT / "chapter-03")
    assert learner.reuse_lesson(SUBJECT, "chapter-03", root=me) is None


def test_hook_stays_silent_while_updating(course):
    owner, upstream, me = course
    owner_pushes(owner, "rules v2", {"AGENTS.md": "# AI Tutor\nversion 2\n"})
    env = {**os.environ, "TUTOR_ROOT": str(me)}
    out = subprocess.run([sys.executable, str(REPO / "tools" / "tutor.py"), "hook", "session-start"],
                         input='{"source": "startup"}', capture_output=True, text=True, env=env, cwd=me)
    assert out.returncode == 0 and out.stderr == ""
    assert set(json.loads(out.stdout)) == {"hookSpecificOutput"}
    assert (me / "AGENTS.md").read_text() == "# AI Tutor\nversion 2\n"
