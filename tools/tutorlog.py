"""Quiet failure handling shared by the tutor's tools.

Bookkeeping must never interrupt teaching: on failure a tool writes one line to
learner/tutor.log, queues the work in learner/pending.jsonl when a retry could help, and
exits 0. The next session start retries the queue (tools/tutor.py). Standard library only.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

MAX_ATTEMPTS = 3

# Packages installed for sharing (with the learner's permission) live in .tutor/pylib, so the
# system Python is never changed. Every tool imports this module first, so they all see them.
_PYLIB = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1]) / ".tutor" / "pylib"
if _PYLIB.is_dir() and str(_PYLIB) not in sys.path:
    sys.path.insert(1, str(_PYLIB))


def _learner(root):
    path = Path(root) / "learner"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log(root, tool, message):
    """Append one line to learner/tutor.log. Never raises."""
    try:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        line = " ".join(f"{stamp} {tool}: {message}".split())
        with (_learner(root) / "tutor.log").open("a", encoding="utf-8") as f:
            f.write(line[:2000] + "\n")
    except Exception:  # the log itself failing must not surface either
        pass


def queue(root, kind, payload, attempts=None):
    """Save work to retry next session. Never raises. During a retry, the attempt number
    comes from TUTOR_RETRY_ATTEMPTS so work that keeps failing is eventually dropped."""
    if attempts is None:
        attempts = int(os.environ.get("TUTOR_RETRY_ATTEMPTS", "0") or 0)
    try:
        entry = {"kind": kind, "payload": payload, "attempts": attempts}
        with (_learner(root) / "pending.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log(root, "tutorlog", f"could not queue {kind} for retry: {exc!r}")


def take_pending(root):
    """Return and clear the retry queue."""
    path = Path(root) / "learner" / "pending.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            log(root, "tutorlog", "dropped an unreadable pending entry")
    path.unlink()
    return entries
