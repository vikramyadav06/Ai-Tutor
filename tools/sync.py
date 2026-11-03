#!/usr/bin/env python3
"""
Multi-device sync (TECH_SPEC §16, Phase 2.5): continue on another device without losing
anything. Runs invisibly in the hooks: pull and merge at session start, push at session end.

    python tools/sync.py pull
    python tools/sync.py push

What syncs: learner/ (except device-local files), my-work/, and lessons and catalogs the tutor
wrote under core/subjects/, plus which sessions were already shared (so no device sends a
session twice). Never .tutor/outbox, never the identity or sync secret, never git-tracked
course content from upstream.

Everything is one encrypted archive per sync (nacl.secret.SecretBox) on the orphan branch
`tutor-sync` of the learner's own fork, with a neutral author and day-rounded dates.
Key: BLAKE2b keyed KDF with a fixed context string, from the adult's learner-code seed or the
student's separate random sync secret. Repo B never reads tutor-sync.

Merging never loses data: session logs are combined line by line; private terms are
combined; notes and progress keep every section; plan statuses keep the furthest progress;
for every other file the newest wins and the other copy is kept in learner/history/.

Prints nothing; failures go to learner/tutor.log and are retried next session.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learner  # noqa: E402
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])
BRANCH = "tutor-sync"
WORKTREE = "sync-worktree"
ARCHIVE_PATH = re.compile(r"^\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.bin$")
KDF_CONTEXT = b"tutor-sync-v1"  # BLAKE2b personalisation (max 16 bytes)
FORMAT = 1
MAX_FILE_BYTES = 1_000_000
MAX_ARCHIVE_BYTES = 8_000_000
SYNC_ROOTS = ("learner", "my-work", "core/subjects")
LEARNER_LOCAL = {"learner/tutor.log", "learner/pending.jsonl", "learner/agent.txt", "learner/sessions/current"}
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".git"}
STATUS_RANK = {"not-started": 0, "in-progress": 1, "done": 2}
SHARED_RANK = {"sent": 5, "rejected": 4, "not-shared": 3, "empty": 2, "dry-run": 1}


class SyncError(Exception):
    pass


# ---------- secrets and keys ----------

def sync_secret(root):
    """32 secret bytes: the adult's signing seed, or the student's sync secret. None if neither."""
    identity = learner.read_json(learner.identity_path(root))
    if identity and identity.get("signing_seed_b64"):
        return base64.b64decode(identity["signing_seed_b64"])
    student = learner.read_json(learner.sync_secret_path(root))
    if student and student.get("sync_secret_b64"):
        return base64.b64decode(student["sync_secret_b64"])
    return None


def derive_key(secret):
    """KDF: BLAKE2b keyed by the secret, with a fixed context, so the sync key is independent
    of the signing key it comes from."""
    from nacl.encoding import RawEncoder
    from nacl.hash import blake2b
    return blake2b(b"", digest_size=32, key=secret, person=KDF_CONTEXT, encoder=RawEncoder)


def box(root, secret=None):
    from nacl.secret import SecretBox
    secret = secret or sync_secret(root)
    if not secret:
        raise SyncError("no learner code or sync code on this device")
    return SecretBox(derive_key(secret))


# ---------- what syncs ----------

def _state_path(root):
    return learner.tutor_dir(root) / "sync_state.json"


def load_state(root):
    return learner.read_json(_state_path(root), {"seen": [], "rejected": [], "last_digest": None})


def save_state(root, state):
    learner.write_private_json(_state_path(root), state)


def _tutor_written(root):
    """Lessons, catalogs and exercise files the tutor wrote here (not upstream course content)."""
    import collect
    folder = Path(root) / "core" / "subjects"
    if not folder.exists() or not (Path(root) / ".git").exists():
        return []
    out = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.is_symlink() and not (SKIP_PARTS & set(path.parts)):
            try:
                if collect.written_here(root, path):
                    out.append(path)
            except Exception:
                continue
    return out


def snapshot_files(root):
    """{relative path: (bytes, mtime)} of everything that syncs."""
    root = Path(root)
    files, total = {}, 0
    candidates = []
    for top in ("learner", "my-work"):
        base = root / top
        if base.exists():
            candidates += [p for p in sorted(base.rglob("*")) if p.is_file() and not p.is_symlink()]
    candidates += _tutor_written(root)
    for path in candidates:
        rel = path.relative_to(root).as_posix()
        if rel in LEARNER_LOCAL or SKIP_PARTS & set(Path(rel).parts) or rel.endswith(".pyc"):
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            tutorlog.log(root, "sync", f"skipped {rel}: over {MAX_FILE_BYTES // 1000} KB")
            continue
        if total + size > MAX_ARCHIVE_BYTES:
            tutorlog.log(root, "sync", f"skipped {rel}: archive would exceed {MAX_ARCHIVE_BYTES // 1000000} MB")
            continue
        total += size
        files[rel] = (path.read_bytes(), path.stat().st_mtime)
    return files


def build_archive(root, secret=None):
    """Encrypted archive bytes, and a digest of the content (to skip pushing when nothing changed)."""
    files = snapshot_files(root)
    collected = learner.read_json(learner.tutor_dir(root) / "collected.json", {"sessions": {}, "lessons": {}})
    content = {"files": {rel: base64.b64encode(data).decode() for rel, (data, _) in sorted(files.items())},
               "collected": collected}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    payload = {"format": FORMAT, "made": dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds"),
               **content, "mtimes": {rel: mtime for rel, (_, mtime) in files.items()}}
    raw = zlib.compress(json.dumps(payload, ensure_ascii=False).encode(), 9)
    return box(root, secret).encrypt(raw), digest


def open_archive(blob, root, secret=None):
    """Decrypt and check an archive. Raises nacl.exceptions.CryptoError if it was tampered with
    or made with another key; SyncError if it doesn't look like a sync archive."""
    raw = box(root, secret).decrypt(blob)
    try:
        payload = json.loads(zlib.decompress(raw))
    except (zlib.error, json.JSONDecodeError) as exc:
        raise SyncError(f"unreadable archive: {exc}")
    if payload.get("format") != FORMAT or not isinstance(payload.get("files"), dict):
        raise SyncError("unknown archive format")
    return payload


# ---------- merging ----------

def safe_rel(rel):
    """Only paths inside the synced folders, never outside the repo."""
    if not isinstance(rel, str) or "\\" in rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return False
    parts = Path(rel).parts
    if ".." in parts or not parts or SKIP_PARTS & set(parts):
        return False
    if rel in LEARNER_LOCAL:
        return False
    return any(rel == r or rel.startswith(r + "/") for r in SYNC_ROOTS)


def _history(root, rel, data, side, stamp):
    path = Path(root) / "learner" / "history" / f"{stamp}-{side}" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _merge_jsonl(local, remote):
    """Append-only logs: every line from both, in time order, each once."""
    local_lines = {line for line in local.decode("utf-8").splitlines() if line.strip()}
    remote_lines = {line for line in remote.decode("utf-8").splitlines() if line.strip()}
    if remote_lines <= local_lines:
        return local  # nothing new from the other device
    if local_lines <= remote_lines:
        return remote  # the other device has everything this one has, and more
    seen, lines = set(), []
    for line in local.decode("utf-8").splitlines() + remote.decode("utf-8").splitlines():
        if line.strip() and line not in seen:
            seen.add(line)
            lines.append(line)

    def when(line):
        try:
            return json.loads(line).get("t", "")
        except json.JSONDecodeError:
            return ""
    lines.sort(key=when)  # stable: same-minute lines keep their order
    return ("\n".join(lines) + "\n").encode("utf-8")


def _merge_terms(local, remote):
    terms = json.loads(local).get("terms", []) + json.loads(remote).get("terms", [])
    seen, out = set(), []
    for term in terms:
        if term.lower() not in seen:
            seen.add(term.lower())
            out.append(term)
    return (json.dumps({"terms": out}, indent=2, ensure_ascii=False) + "\n").encode()


DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _merge_sections(local, remote, newest_first):
    """Markdown notes ('## ' sections, oldest first) and progress ('### ' entries, newest first):
    keep every section from both, ordered by the date in it. The header is left alone."""
    heading = re.compile(r"^(?=### )" if newest_first else r"^(?=## )", re.M)

    def split(text):
        parts = heading.split(text)
        head, blocks = parts[0], [b.rstrip() + "\n" for b in parts[1:]]
        return head, blocks
    lhead, lblocks = split(local.decode("utf-8"))
    rhead, rblocks = split(remote.decode("utf-8"))
    local_set, remote_set = {b.strip() for b in lblocks}, {b.strip() for b in rblocks}
    if remote_set <= local_set:
        return local  # nothing new from the other device
    if local_set <= remote_set and lhead.strip() == rhead.strip():
        return remote  # the other device has everything this one has, and more
    blocks, seen = [], set()
    for block in lblocks + rblocks:
        if block.strip() not in seen:
            seen.add(block.strip())
            blocks.append(block)

    def when(block):
        m = DATE.search(block)
        return m.group(0) if m else ""
    blocks.sort(key=when, reverse=newest_first)
    head = lhead if lhead.strip() else rhead
    joiner = "" if newest_first else "\n"
    return (head.rstrip() + "\n" + ("" if newest_first else "\n") + joiner.join(blocks)).encode("utf-8")


def _merge_plan(newer, older):
    """The newer plan's shape, with the furthest progress either device made."""
    new, old = json.loads(newer), json.loads(older)
    old_status = {m["id"]: m.get("status", "not-started") for m in old.get("modules", [])}
    for m in new.get("modules", []):
        theirs = old_status.get(m["id"])
        if theirs and STATUS_RANK.get(theirs, 0) > STATUS_RANK.get(m.get("status"), 0):
            m["status"] = theirs
    return (json.dumps(new, indent=2, ensure_ascii=False) + "\n").encode()


def merge_file(root, rel, remote, remote_mtime, stamp):
    """Bring one remote file in. Returns True if the local copy changed."""
    path = Path(root) / rel
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(remote)
        os.utime(path, (remote_mtime, remote_mtime))
        return True
    local = path.read_bytes()
    if local == remote:
        return False
    local_mtime = path.stat().st_mtime
    try:
        if rel.startswith("learner/sessions/") and rel.endswith(".jsonl"):
            merged = _merge_jsonl(local, remote)
        elif rel == "learner/private_terms.json":
            merged = _merge_terms(local, remote)
        elif rel.startswith("learner/subjects/") and rel.endswith(("/notes.md", "/progress.md")):
            merged = _merge_sections(local, remote, newest_first=rel.endswith("/progress.md"))
        elif rel.startswith("learner/subjects/") and rel.endswith("/plan.json"):
            newer, older = (remote, local) if remote_mtime > local_mtime else (local, remote)
            _history(root, rel, older, "older", stamp)
            merged = _merge_plan(newer, older)
        else:
            merged = None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        merged = None  # unexpected content: fall back to newest-wins, keeping both
    if merged is None:
        if remote_mtime > local_mtime:
            _history(root, rel, local, "replaced", stamp)  # the local copy is kept, never lost
            path.write_bytes(remote)
            os.utime(path, (remote_mtime, remote_mtime))
            return True
        _history(root, rel, remote, "other-device", stamp)
        return False
    if merged != local:
        path.write_bytes(merged)
        return True
    return False


def merge_collected(root, remote):
    """Union of what each device already shared, so nothing is sent twice."""
    path = learner.tutor_dir(root) / "collected.json"
    local = learner.read_json(path, {"sessions": {}, "lessons": {}})
    for sid, value in (remote.get("sessions") or {}).items():
        mine = local["sessions"].get(sid)
        if mine is None or SHARED_RANK.get(value, 0) > SHARED_RANK.get(mine, 0):
            local["sessions"][sid] = value
    for rel, digest in (remote.get("lessons") or {}).items():
        local["lessons"].setdefault(rel, digest)
    learner.write_private_json(path, local)


def merge_archive(root, payload):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    changed = []
    mtimes = payload.get("mtimes", {})
    for rel, b64 in payload["files"].items():
        if not safe_rel(rel):
            tutorlog.log(root, "sync", f"ignored an unsafe path in an archive: {rel!r}")
            continue
        if merge_file(root, rel, base64.b64decode(b64), float(mtimes.get(rel, 0)), stamp):
            changed.append(rel)
    merge_collected(root, payload.get("collected") or {})
    return changed


# ---------- git transport ----------

def _publish():
    import publish
    return publish


def sync_enabled(root):
    profile = learner.read_json(learner.learner_dir(root) / "profile.json", {})
    return profile.get("sync", True) is not False


def fetch_archives(root, gh=None):
    """[(name, blob)] from origin's tutor-sync, or a status string."""
    publish = _publish()
    if not (Path(root) / ".git").exists():
        return "no-git"
    if not publish.ensure_fork(root, publish.upstream_repo(root), gh):
        return "needs-gh-auth"
    if not publish.remote_has_branch(root, BRANCH):
        return []
    ref = f"refs/remotes/origin/{BRANCH}"
    publish.git(root, "fetch", "--no-tags", "--quiet", "origin", f"+refs/heads/{BRANCH}:{ref}", timeout=120)
    names = publish.git(root, "ls-tree", "-r", "--name-only", ref).stdout.split()
    out = []
    for name in names:
        if not ARCHIVE_PATH.match(name):
            continue
        blob = subprocess.run(["git", "cat-file", "blob", f"{ref}:{name}"], cwd=root,
                              capture_output=True, timeout=60)
        if blob.returncode == 0:
            out.append((name, blob.stdout))
    return out


def pull(root=None, gh=None, secret=None):
    """Merge every archive not seen yet. Returns 'merged:<n>', 'nothing', 'off', 'no-secret',
    'needs-gh-auth', 'no-git', or 'wrong-key' (archives exist but none opened with this code)."""
    from nacl.exceptions import CryptoError
    root = Path(root or ROOT)
    secret = secret or sync_secret(root)
    if not secret:
        return "no-secret"
    if (learner.learner_dir(root) / "profile.json").exists() and not sync_enabled(root):
        return "off"
    archives = fetch_archives(root, gh)
    if isinstance(archives, str):
        return archives
    state = load_state(root)
    merged = opened_any = 0
    tried_new = 0
    opened = []
    for name, blob in sorted(archives):
        if name in state["seen"] or name in state["rejected"]:
            opened_any += name in state["seen"]
            continue
        tried_new += 1
        try:
            opened.append((name, open_archive(blob, root, secret)))
        except (CryptoError, SyncError) as exc:
            tutorlog.log(root, "sync", f"rejected archive {name}: {type(exc).__name__}")
            state["rejected"].append(name)
    for name, payload in sorted(opened, key=lambda item: str(item[1].get("made", ""))):  # oldest first
        merge_archive(root, payload)
        state["seen"].append(name)
        merged += 1
        opened_any += 1
    if merged:
        state["last_digest"] = None  # local data changed: the next push is a real one
    save_state(root, state)
    if tried_new and not opened_any:
        return "wrong-key"
    return f"merged:{merged}" if merged else "nothing"


def push(root=None, gh=None, day=None):
    """Push one archive if anything changed since the last push. Returns a status string."""
    root = Path(root or ROOT)
    if not sync_secret(root):
        return "no-secret"
    if not sync_enabled(root):
        return "off"
    if not (root / ".git").exists():
        return "no-git"
    state = load_state(root)
    blob, digest = build_archive(root)
    if digest == state.get("last_digest"):
        return "unchanged"
    publish = _publish()
    if not publish.ensure_fork(root, publish.upstream_repo(root), gh):
        return "needs-gh-auth"
    day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    name = f"{day}/{uuid.uuid4().hex}.bin"
    with tempfile.TemporaryDirectory(dir=learner.tutor_dir(root)) as tmp:
        src = Path(tmp) / "archive.bin"
        src.write_bytes(blob)
        publish.push_orphan(root, [(name, src)], BRANCH, WORKTREE, ARCHIVE_PATH, "sync", day)
    state["seen"].append(name)
    state["last_digest"] = digest
    save_state(root, state)
    return "pushed"


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["pull", "push"])
    args = parser.parse_args(argv)
    try:
        result = pull() if args.action == "pull" else push()
        if result in ("wrong-key", "needs-gh-auth"):
            tutorlog.log(ROOT, "sync", f"{args.action}: {result}")
    except Exception as exc:
        tutorlog.log(ROOT, "sync", f"{args.action} failed, will retry next session: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
