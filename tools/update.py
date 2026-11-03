#!/usr/bin/env python3
"""
Course updates (TECH_SPEC §17, Phase 2.5): at session start the hook silently fetches upstream
main and brings the learner's copy up to date: core/, AGENTS.md, CLAUDE.md, tools/, the hooks
and settings, requirements and project.json (new collector keys arrive this way).

    python tools/update.py

Rules:
- Never touches learner/, my-work/ or .tutor/, and nothing outside the course paths.
- Never rewrites history: a true fast-forward (`git merge --ff-only`) when the learner's branch
  has no commits of its own and a clean tree; otherwise each course file is updated with a
  three-way check against the last applied upstream version, and one new commit is added.
  Never rebase, reset or force.
- A file the learner's copy changed and upstream also changed is kept as it is (logged), except:
  a reviewed lesson replaces the tutor's unreviewed one for the same chapter. The local copy is
  kept in learner/history/ and the learner's progress in that chapter is mapped across.
- Offline, a conflict, an unusual git state: teaching continues on the current copy; it is
  retried next session. Prints nothing; problems go to learner/tutor.log.
"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learner  # noqa: E402
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])
UPSTREAM_REF = "refs/tutor-upstream/main"
MANAGED = ("core/", "tools/", ".claude/", ".github/", "docs/", "AGENTS.md", "CLAUDE.md", "README.md",
           "project.json", "requirements-tutor.txt", "requirements-dev.txt", "pytest.ini", ".gitignore")
NEVER = ("learner/", "my-work/", ".tutor/")


class UpdateError(Exception):
    pass


def git(root, *args, check=True, timeout=60, binary=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=not binary, env=env, timeout=timeout)
    if check and result.returncode != 0:
        err = result.stderr if not binary else result.stderr.decode("utf-8", "replace")
        raise UpdateError(f"git {args[0]} failed: {err.strip()[:300]}")
    return result


def managed(path):
    if path.startswith(NEVER) or "/../" in f"/{path}/":
        return False
    return any(path == m or (m.endswith("/") and path.startswith(m)) for m in MANAGED)


def upstream_url(root):
    if os.environ.get("TUTOR_UPSTREAM_URL"):  # tests only: a local stand-in for GitHub
        return os.environ["TUTOR_UPSTREAM_URL"]
    repo = json.loads((Path(root) / "project.json").read_text(encoding="utf-8"))["upstream_repo"]
    return f"https://github.com/{repo}.git"


def _state_path(root):
    return learner.tutor_dir(root) / "update_state.json"


def blob(root, rev, path):
    out = git(root, "cat-file", "blob", f"{rev}:{path}", check=False, binary=True)
    return out.stdout if out.returncode == 0 else None


def busy(root):
    """An unusual git state where we must not commit (merge, rebase, detached head...)."""
    gitdir = Path(git(root, "rev-parse", "--absolute-git-dir").stdout.strip())
    for marker in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG"):
        if (gitdir / marker).exists():
            return f"git is in the middle of something ({marker})"
    if git(root, "symbolic-ref", "-q", "HEAD", check=False).returncode != 0:
        return "detached HEAD"
    return None


def update(root=None):
    """Returns 'offline', 'busy:<why>', 'up-to-date', 'fast-forward', 'updated:<n>' or
    'partial:<n>' (some files kept local; retried next time)."""
    root = Path(root or ROOT)
    if not (root / ".git").exists() or not (learner.learner_dir(root) / "profile.json").exists():
        return "not-a-learner-copy"  # never update a developer's checkout
    why = busy(root)
    if why:
        return f"busy:{why}"
    fetched = git(root, "fetch", "--quiet", "--no-tags", upstream_url(root), f"+refs/heads/main:{UPSTREAM_REF}",
                  check=False, timeout=30)
    if fetched.returncode != 0:
        return "offline"
    upstream = git(root, "rev-parse", UPSTREAM_REF).stdout.strip()
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    state = learner.read_json(_state_path(root), {})
    base = state.get("applied")
    if not base or git(root, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode != 0:
        mb = git(root, "merge-base", "HEAD", upstream, check=False)
        if mb.returncode != 0:
            return "busy:no common history with upstream"
        base = mb.stdout.strip()
    if base == upstream or git(root, "merge-base", "--is-ancestor", upstream, "HEAD", check=False).returncode == 0:
        learner.write_private_json(_state_path(root), {**state, "applied": upstream})
        return "up-to-date"

    # a true fast-forward when nothing local is in the way
    clean = git(root, "status", "--porcelain", "--untracked-files=all").stdout.strip() == ""
    if head == base and clean:
        before = lesson_snapshot(root)
        if git(root, "merge", "--ff-only", "--quiet", upstream, check=False).returncode == 0:
            learner.write_private_json(_state_path(root), {**state, "applied": upstream})
            after_lesson_changes(root, before)
            return "fast-forward"

    # otherwise: course paths only, file by file, one new commit
    changed = git(root, "diff", "--name-status", "--no-renames", "-z", base, upstream).stdout.split("\0")
    pairs = [(changed[i], changed[i + 1]) for i in range(0, len(changed) - 1, 2)]
    applied, kept, replaced = [], [], {}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    for status, path in pairs:
        if not managed(path):
            continue
        target = root / path
        local = target.read_bytes() if target.is_file() else None
        old = blob(root, base, path)
        new = blob(root, upstream, path) if status != "D" else None
        if local == new:
            continue
        if local is None or local == old:
            write_or_delete(root, path, new)
            applied.append(path)
        elif new is not None and is_lesson(path) and reviewed_replaces(local, new):
            keep_copy(root, path, local, stamp)
            replaced[path] = json.loads(local)
            write_or_delete(root, path, new)
            applied.append(path)
        elif new is not None and old is None and path.startswith("core/subjects/"):
            # the tutor wrote this file here and upstream now has its own (reviewed) version
            keep_copy(root, path, local, stamp)
            write_or_delete(root, path, new)
            applied.append(path)
        else:
            kept.append(path)
            tutorlog.log(root, "update", f"kept the local {path}: changed here and upstream")
    if applied:
        commit(root, applied, upstream)
    for path, old_lesson in replaced.items():
        carry_progress(root, path, old_lesson)
    if not kept:
        learner.write_private_json(_state_path(root), {**state, "applied": upstream})
        return f"updated:{len(applied)}"
    return f"partial:{len(applied)}"


def is_lesson(path):
    parts = Path(path).parts
    return len(parts) == 5 and parts[:2] == ("core", "subjects") and parts[4] == "lesson.json"


def reviewed_replaces(local, new):
    try:
        mine, theirs = json.loads(local), json.loads(new)
    except (ValueError, UnicodeDecodeError):
        return False
    return mine.get("status") != "reviewed" and theirs.get("status") == "reviewed"


def keep_copy(root, path, data, stamp):
    dest = learner.learner_dir(root) / "history" / f"{stamp}-before-update" / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def write_or_delete(root, path, data):
    target = Path(root) / path
    if data is None:
        if target.exists():
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tutor-update")
    tmp.write_bytes(data)
    os.replace(tmp, target)


def commit(root, paths, upstream):
    """One commit with the updated course files only; nothing else the learner staged."""
    for i in range(0, len(paths), 100):
        git(root, "add", "-A", "--", *paths[i:i + 100])
    if git(root, "diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
        return
    identity = []
    if not git(root, "config", "user.email", check=False).stdout.strip():
        identity = ["-c", "user.name=tutor", "-c", "user.email=tutor@invalid"]
    git(root, *identity, "-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify",
        "-m", f"tutor: course update to {upstream[:12]}", "--", *paths)


def lesson_snapshot(root):
    """Unreviewed lessons before a fast-forward, to notice reviewed replacements."""
    out = {}
    for path in (Path(root) / "core" / "subjects").glob("*/*/lesson.json"):
        try:
            lesson = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if lesson.get("status") != "reviewed":
            out[path.relative_to(root).as_posix()] = lesson
    return out


def after_lesson_changes(root, before):
    for path, old_lesson in before.items():
        new = learner.read_json(Path(root) / path)
        if new and new.get("status") == "reviewed":
            carry_progress(root, path, old_lesson)


def carry_progress(root, path, old_lesson):
    """The learner keeps their place in a chapter whose lesson was replaced."""
    _, _, subject, module, _ = Path(path).parts
    plan_path = learner.subject_dir(subject, root) / "plan.json"
    plan = learner.read_json(plan_path)
    new_lesson = learner.read_json(Path(root) / path)
    if not plan or not new_lesson:
        return
    for row in plan.get("modules", []):
        if row["id"] == module and row.get("batches_done"):
            row["batches_done_before_review"] = row["batches_done"]
            row["batches_done"] = learner.map_batches(row["batches_done"], old_lesson, new_lesson)
            row["lesson_replaced"] = dt.date.today().isoformat()  # the chapter's status stays as it was
    learner.write_json(plan_path, plan)


def main():
    try:
        result = update()
        if result.startswith(("busy", "partial")):
            tutorlog.log(ROOT, "update", result)
    except Exception as exc:
        tutorlog.log(ROOT, "update", f"failed, will retry next session: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
