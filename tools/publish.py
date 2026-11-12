#!/usr/bin/env python3
"""
Commit the encrypted outbox to the orphan `tutor-data` branch of the learner's fork and push
that branch only (TECH_SPEC §8). Runs invisibly at session end (tools/tutor.py finish).

    python tools/publish.py

- The branch is built in a separate worktree at .tutor/worktree, so the learner's own
  working tree and branches are never touched.
- It holds only <key_id>/<YYYY-MM-DD>/<uuid hex>.bin files.
- Commits use a neutral identity (tutor <tutor@invalid>) and day-rounded dates.
- Only `tutor-data` is ever pushed; `main` and every other branch are never pushed.
- If origin is the upstream Repo A, it forks with `gh` (origin becomes the fork, the
  upstream becomes `upstream`). If gh is missing or signed out, files stay in the outbox,
  the tutor asks the learner once to run `gh auth login`, and it retries next session.

Does nothing while collector.enabled is false. Prints nothing; failures go to
learner/tutor.log and are retried next session.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402
import learner  # noqa: E402
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])
BRANCH = "tutor-data"
DATA_PATH = re.compile(r"^k\d+/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.bin$")
NEUTRAL = {"GIT_AUTHOR_NAME": "tutor", "GIT_AUTHOR_EMAIL": "tutor@invalid",
           "GIT_COMMITTER_NAME": "tutor", "GIT_COMMITTER_EMAIL": "tutor@invalid"}
NEEDS_GH = "needs_gh_auth"


class PublishError(Exception):
    pass


def git(cwd, *args, env=None, timeout=60, check=True):
    full_env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=full_env, timeout=timeout)
    if check and result.returncode != 0:
        raise PublishError(f"git {args[0]} failed: {result.stderr.strip()[:300]}")
    return result


def outbox_files(root):
    outbox = learner.tutor_dir(root) / "outbox"
    if not outbox.exists():
        return []
    files = []
    for path in sorted(outbox.rglob("*.bin")):
        rel = path.relative_to(outbox).as_posix()
        if DATA_PATH.match(rel):
            files.append((rel, path))
        else:
            tutorlog.log(root, "publish", f"ignored an outbox file with an unexpected name: {rel}")
    return files


def is_upstream(url, upstream_repo):
    """True if url is the upstream repo, or one of its former names (a str or a list)."""
    url = (url or "").strip().lower().rstrip("/")
    url = url[:-4] if url.endswith(".git") else url
    repos = [upstream_repo] if isinstance(upstream_repo, str) else list(upstream_repo)
    return any(url.endswith("github.com/" + r.lower()) or url.endswith("github.com:" + r.lower())
               for r in repos)


def ensure_fork(root, upstream_repo, gh=None):
    """Make origin the learner's own fork. Returns False if gh can't do it yet."""
    origin = git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    if origin and not is_upstream(origin, upstream_repo):
        return True
    gh = gh or shutil.which("gh")
    flag = learner.tutor_dir(root) / NEEDS_GH
    if not gh or subprocess.run([gh, "auth", "status"], cwd=root, capture_output=True, timeout=30).returncode != 0:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("gh is missing or signed out\n", encoding="utf-8")
        return False
    done = subprocess.run([gh, "repo", "fork", "--remote", "--remote-name", "origin"], cwd=root,
                          capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise PublishError(f"gh repo fork failed: {done.stderr.strip()[:300]}")
    if flag.exists():
        flag.unlink()
    return True


def remote_has_branch(root, branch=BRANCH):
    out = git(root, "ls-remote", "--heads", "origin", branch, timeout=60, check=False)
    return out.returncode == 0 and bool(out.stdout.strip())


def ensure_worktree(root, branch=BRANCH, name="worktree"):
    """A worktree on an orphan branch at .tutor/<name>, never the learner's own checkout."""
    wt = learner.tutor_dir(root) / name
    if wt.exists() and (wt / ".git").exists():
        head = git(wt, "symbolic-ref", "--short", "HEAD", check=False).stdout.strip()
        if head == branch:
            return wt
        git(root, "worktree", "remove", "--force", str(wt), check=False)
    if wt.exists():
        shutil.rmtree(wt)
    git(root, "worktree", "prune", check=False)
    has_local = git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
    if not has_local and remote_has_branch(root, branch):
        git(root, "fetch", "--no-tags", "origin", f"+refs/heads/{branch}:refs/heads/{branch}")
        has_local = True
    if has_local:
        git(root, "worktree", "add", "--quiet", str(wt), branch)
    else:
        git(root, "worktree", "add", "--quiet", "--detach", str(wt))
        git(wt, "checkout", "--quiet", "--orphan", branch)
        git(wt, "rm", "-r", "--quiet", "--cached", "--ignore-unmatch", ".")
        git(wt, "clean", "-fdxq")
    return wt


def check_branch_contents(wt, branch=BRANCH, path_re=DATA_PATH):
    files = git(wt, "ls-files").stdout.split()
    bad = [f for f in files if not path_re.match(f)]
    if bad:
        raise PublishError(f"{branch} would contain unexpected files: {bad[:3]}")


def push_orphan(root, files, branch, name, path_re, message, day=None):
    """Add (published path, source file) pairs to an orphan branch and push only that branch,
    with a neutral identity and day-rounded dates. Used for tutor-data and tutor-sync."""
    for rel, _ in files:
        if not path_re.match(rel):
            raise PublishError(f"refusing to add {rel!r} to {branch}")
    wt = ensure_worktree(root, branch, name)
    for rel, src in files:
        dest = wt / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        git(wt, "add", "--", rel)
    check_branch_contents(wt, branch, path_re)
    day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    stamp = f"{day}T00:00:00Z"
    env = {**NEUTRAL, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    if git(wt, "diff", "--cached", "--quiet", check=False).returncode != 0:
        git(wt, "-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", message, env=env)

    refspec = f"refs/heads/{branch}:refs/heads/{branch}"  # this branch and nothing else
    pushed = git(wt, "push", "--quiet", "--no-verify", "origin", refspec, env=env, timeout=120, check=False)
    if pushed.returncode != 0:
        # the learner's other device pushed first: replay ours on top, once
        git(wt, "fetch", "--no-tags", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        git(wt, "-c", "commit.gpgsign=false", "rebase", "--quiet", f"refs/remotes/origin/{branch}", env=env)
        check_branch_contents(wt, branch, path_re)
        git(wt, "push", "--quiet", "--no-verify", "origin", refspec, env=env, timeout=120)


def upstream_repo(root):
    """The upstream repo and its former names: a clone made before a rename or transfer still
    points origin at an old name, and must never be mistaken for the learner's own fork."""
    project = json.loads((Path(root) / "project.json").read_text(encoding="utf-8"))
    return [project["upstream_repo"], *project.get("former_upstream_repos", [])]


def publish(root=None, config=None, gh=None, day=None):
    """Returns what happened: disabled, nothing, needs-gh-auth or pushed:<n>."""
    root = Path(root or ROOT)
    config = config or collect.load_config(root)
    if not config.get("enabled"):
        return "disabled"
    if config.get("data_branch", BRANCH) != BRANCH:
        raise PublishError("data_branch must be tutor-data")
    files = outbox_files(root)
    if not files:
        return "nothing"
    if not collect.keys_trusted(root):
        tutorlog.log(root, "keys", "held: collector keys changed and aren't trusted yet; nothing published")
        return "held-key-change"
    if not (root / ".git").exists():
        raise PublishError("not a git repository")
    if not ensure_fork(root, upstream_repo(root), gh):
        return "needs-gh-auth"
    push_orphan(root, files, BRANCH, "worktree", DATA_PATH, "data", day)
    for _, src in files:
        src.unlink()
    return f"pushed:{len(files)}"


def main():
    try:
        publish()
    except Exception as exc:
        tutorlog.log(ROOT, "publish", f"failed, will retry next session: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
