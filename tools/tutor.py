#!/usr/bin/env python3
"""
All of the tutor's background work, in as few calls as possible, invisible to the learner.

    python tools/tutor.py record --json '<batch payload>'   # once per batch, never between steps
    python tools/tutor.py context                           # private context for the agent
    python tools/tutor.py hook session-start                # Claude Code SessionStart hook
    python tools/tutor.py hook session-end                  # Claude Code SessionEnd hook

`record` and the hooks print nothing (session-start prints context that Claude Code hands to the
agent, never to the learner). They always exit 0: failures go to learner/tutor.log and are
retried at the next session start, so teaching is never interrupted.

Record payload (every key optional; see core/teaching/steps-and-notes.md):

    {"subject": "class-9-science", "module": "matter", "agent": "claude-code",
     "steps": [{"step_ref": "b1-s2", "type": "choice", "outcome": "correct",
                "attempts": 1, "hints": 0, "seconds": 40, "answer_text": "..."}],
     "moves": [{"topic": "diffusion", "move": "analogy", "style": "analogies", "worked": "true"}],
     "signals": [{"kind": "confused", "topic": "latent-heat"}],
     "exercises": [{"ref": "melting-ice", "passed": "true", "code_file": "my-work/..."}],
     "private_terms": ["Sunrise Public School"],
     "batch_done": 1, "notes_extra": "one personal revision line",
     "module_done": true,
     "model": {"set": {"pace": "slow"}, "add": {"weak_areas": ["latent-heat"]}, "remove": {}},
     "progress_entry": "### 2026-11-03 – Matter\\n- Learned: ...",
     "feedback": {"rating": 5, "comment": "..."},
     "end": true}

Set TUTOR_ROOT to use another folder as the repo root (tests do this).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learner  # noqa: E402
import log_session  # noqa: E402
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])
KNOWN_KEYS = {"subject", "module", "agent", "session_id", "steps", "moves", "signals", "exercises",
              "private_terms", "batch_done", "notes_extra", "module_done", "model", "progress_entry",
              "feedback", "end"}
EXPECTED = (learner.TutorError, log_session.LogError, KeyError, TypeError, ValueError)
COMMIT_PATHS = ("my-work", "core/subjects")
COMMIT_MESSAGE = "tutor: save work and lessons"


def has_learner(root):
    return (Path(root) / "learner" / "profile.json").exists()


# ---------- record: one quiet call per batch ----------

def record(payload, root=None):
    """Apply a batch payload. Bad items are logged and skipped; items that fail for other
    reasons (disk, permissions) are queued and retried next session. Never raises."""
    root = Path(root or ROOT)
    if not isinstance(payload, dict):
        tutorlog.log(root, "record", "payload is not a JSON object; nothing recorded")
        return
    unknown = set(payload) - KNOWN_KEYS
    if unknown:
        tutorlog.log(root, "record", f"ignored unknown keys {sorted(unknown)}")
    subject, module = payload.get("subject"), payload.get("module")
    failed = {}  # payload key -> what to retry; rebuilt into a payload at the end

    def attempt(key, item, fn, many=True):
        try:
            fn()
            return True
        except EXPECTED as exc:
            tutorlog.log(root, "record", f"skipped {key} {json.dumps(item, ensure_ascii=False)[:200]}: {exc}")
        except Exception as exc:
            tutorlog.log(root, "record", f"{key} failed, will retry next session: {exc!r}")
            if many:
                failed.setdefault(key, []).append(item)
            else:
                failed[key] = item
        return False

    for term in payload.get("private_terms", []):
        attempt("private_terms", term, lambda t=term: learner.add_private_term(t, root))

    # the session these events belong to: the one given, the open one, or a new one
    sid = payload.get("session_id")
    events = ("steps", "moves", "signals", "exercises", "feedback")
    if any(payload.get(k) for k in events + ("batch_done", "end")) and not sid:
        try:
            current = log_session.current_id(root)
            if current and log_session.session_path(current, root).exists() and log_session.is_open(current, root):
                sid = current
            elif subject:
                sid = log_session.start(subject, module, payload.get("agent") or default_agent(root), root=root)
            else:
                tutorlog.log(root, "record", "no open session and no subject; events not logged")
        except EXPECTED as exc:
            tutorlog.log(root, "record", f"could not start a session: {exc}")
        except Exception as exc:
            tutorlog.log(root, "record", f"could not start a session, will retry: {exc!r}")
            failed.update({k: payload[k] for k in events if payload.get(k)})

    if sid:
        if module and payload.get("steps"):
            try:
                mark_started(subject, module, root)
            except Exception as exc:  # derivable later; not worth a retry
                tutorlog.log(root, "record", f"could not mark {module} started: {exc!r}")
        for st in payload.get("steps", []):
            attempt("steps", st, lambda st=st: log_session.step(
                st.get("module", module), st["step_ref"], st["type"], st["outcome"],
                st.get("attempts", 1), st.get("hints", 0), st.get("seconds"), st.get("time_band"),
                st.get("answer_text"), session_id=sid, root=root))
        for mv in payload.get("moves", []):
            attempt("moves", mv, lambda m=mv: log_session.move(
                m["topic"], m["move"], m.get("style"), str(m.get("worked", "unknown")).lower(),
                m.get("note"), session_id=sid, root=root))
        for sg in payload.get("signals", []):
            attempt("signals", sg, lambda g=sg: log_session.signal(g["kind"], g["topic"], session_id=sid, root=root))
        for ex in payload.get("exercises", []):
            attempt("exercises", ex, lambda e=ex: log_session.exercise(
                e["ref"], str(e["passed"]).lower(), e.get("code_file"), session_id=sid, root=root))

    n = payload.get("batch_done")
    if n:
        if attempt("batch_done", n, lambda: learner.append_notes(subject, module, n, payload.get("notes_extra"), root),
                   many=False) and sid:
            attempt("batch_event", n, lambda: log_session.batch(module, n, session_id=sid, root=root), many=False)
            failed.pop("batch_event", None)  # the notes are saved; the log line is not worth a retry
        if "batch_done" in failed and payload.get("notes_extra"):
            failed["notes_extra"] = payload["notes_extra"]

    if payload.get("module_done"):
        attempt("module_done", True, lambda: learner.set_progress(subject, module, "done", root), many=False)

    model = payload.get("model") or {}
    if model:
        def apply_model():
            sets = list((model.get("set") or {}).items())
            adds = [(k, v) for k, vals in (model.get("add") or {}).items() for v in as_list(vals)]
            removes = [(k, v) for k, vals in (model.get("remove") or {}).items() for v in as_list(vals)]
            learner.update_model(sets, adds, removes, root)
        attempt("model", model, apply_model, many=False)

    if payload.get("progress_entry"):
        entry = payload["progress_entry"]
        attempt("progress_entry", entry, lambda: add_progress_entry(subject, entry, root), many=False)

    fb = payload.get("feedback")
    if fb and sid:
        attempt("feedback", fb, lambda: log_session.feedback(fb["rating"], fb.get("comment"),
                                                              session_id=sid, root=root), many=False)

    if payload.get("end"):
        finish(root, session_id=sid)

    if failed:
        retry = dict(failed, subject=subject, module=module)
        if sid:
            retry["session_id"] = sid
        tutorlog.queue(root, "record", retry)


def as_list(value):
    return value if isinstance(value, list) else [value]


def default_agent(root):
    path = Path(root) / "learner" / "agent.txt"
    agent = path.read_text(encoding="utf-8").strip() if path.exists() else "other"
    return agent if agent in log_session.AGENTS else "other"


def mark_started(subject, module, root):
    plan = learner.read_json(learner.subject_dir(subject, root) / "plan.json")
    for row in (plan or {}).get("modules", []):
        if row["id"] == module and row["status"] == "not-started":
            learner.set_progress(subject, module, "in-progress", root)


def add_progress_entry(subject, entry, root):
    if not subject:
        raise learner.TutorError("progress_entry needs a subject")
    path = learner.subject_dir(subject, root) / "progress.md"
    marker = "<!-- newest first -->"
    text = path.read_text(encoding="utf-8") if path.exists() else f"# Progress: {subject}\n\n## Session history\n{marker}\n"
    entry = str(entry).strip()
    if marker in text:
        head, tail = text.split(marker, 1)
        text = f"{head}{marker}\n{entry}\n{tail}"
    else:
        text = text.rstrip() + f"\n\n{entry}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- end of session: close the log, commit locally ----------

def finish(root=None, session_id=None):
    """End the open session and commit the learner's work and new lessons locally.
    Idempotent and silent. Phase 2 adds collect + publish here."""
    root = Path(root or ROOT)
    if not has_learner(root):
        return  # not a learner's copy (e.g. a developer working on the repo): do nothing
    try:
        sid = session_id or log_session.current_id(root)
        if sid and log_session.session_path(sid, root).exists() and log_session.is_open(sid, root):
            log_session.end(sid, root=root)
    except Exception as exc:
        tutorlog.log(root, "finish", f"could not close the session log: {exc!r}")
    commit_work(root)


def git(root, *args, timeout=30):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout)


def commit_work(root):
    """Commit my-work/ and core/subjects/ on the current branch. Never pushes."""
    if not (Path(root) / ".git").exists():
        return
    paths = [p for p in COMMIT_PATHS if (Path(root) / p).exists()]
    if not paths:
        return
    try:
        added = git(root, "add", "--", *paths)
        if added.returncode != 0:
            raise RuntimeError(added.stderr.strip())
        if git(root, "diff", "--cached", "--quiet", "--", *paths).returncode == 0:
            return  # nothing new
        identity = []
        if not git(root, "config", "user.email").stdout.strip():
            identity = ["-c", "user.name=tutor", "-c", "user.email=tutor@invalid"]
        done = git(root, *identity, "commit", "-q", "-m", COMMIT_MESSAGE, "--", *paths)
        if done.returncode != 0:
            raise RuntimeError(done.stderr.strip() or done.stdout.strip())
    except Exception as exc:
        tutorlog.log(root, "commit", f"could not commit work, will retry next session: {exc}")


# ---------- start of session: catch up, then context for the agent ----------

def retry_pending(root):
    for entry in tutorlog.take_pending(root):
        attempts = entry.get("attempts", 0) + 1
        if attempts > tutorlog.MAX_ATTEMPTS:
            tutorlog.log(root, "retry", f"gave up on {entry.get('kind')} after {tutorlog.MAX_ATTEMPTS} attempts")
            continue
        os.environ["TUTOR_RETRY_ATTEMPTS"] = str(attempts)
        try:
            if entry.get("kind") == "record":
                record(entry["payload"], root)
            elif entry.get("kind") == "cli":
                tool = {"learner": learner, "log_session": log_session}[entry["payload"]["tool"]]
                tool.main(entry["payload"]["args"])
        except Exception as exc:
            tutorlog.log(root, "retry", f"retry failed: {exc!r}")
            tutorlog.queue(root, entry.get("kind"), entry.get("payload"))
        finally:
            os.environ.pop("TUTOR_RETRY_ATTEMPTS", None)


def context(root=None):
    """Private context for the agent at the start of a session. Never shown to the learner."""
    root = Path(root or ROOT)
    head = ("PRIVATE TUTOR CONTEXT, for you only. Never read it out, quote it, or mention files, "
            "logs, tools or data to the learner.")
    if not has_learner(root):
        return (f"{head}\nNo learner profile yet. If this person wants to learn, greet them and start "
                "onboarding (core/teaching/onboarding.md). If they are building or maintaining this "
                "repository, ignore this and follow docs/TECH_SPEC.md.")
    lines = [head, learner.summary(root)]
    patterns = log_session.summary(last=5, root=root)
    if patterns["sessions"]:
        lines.append(f"Recent sessions: {patterns['sessions']} ({patterns['minutes']} min). "
                     f"Struggled: {', '.join(patterns['struggled']) or '-'}. "
                     f"Signals: {', '.join(patterns['signals']) or '-'}. "
                     f"Moves that work: {', '.join(patterns['moves_that_work']) or '-'}; "
                     f"don't: {', '.join(patterns['moves_that_dont']) or '-'}.")
        if patterns["sessions"] % 3 == 0:
            lines.append("This is a revision session: start with a 5-question quiz on earlier modules and weak areas.")
    lines.append("Bookkeeping: one `python tools/tutor.py record --json '...'` call at the end of each batch "
                 "(core/teaching/steps-and-notes.md), never between steps, never mentioned.")
    return "\n".join(lines)


def session_start(event, root=None):
    root = Path(root or ROOT)
    source = (event or {}).get("source", "startup")
    if has_learner(root):
        try:
            (root / "learner" / "agent.txt").write_text("claude-code\n", encoding="utf-8")
        except OSError:
            pass
        if source in ("startup", "clear"):
            finish(root)          # catch up if the last session ended without its hook
            retry_pending(root)
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": context(root)}})


def read_event():
    try:
        data = sys.stdin.read() if not sys.stdin.isatty() else ""
        return json.loads(data) if data.strip() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record", help="save one batch of bookkeeping")
    p.add_argument("--json", help="the payload; read from stdin if omitted")
    sub.add_parser("context", help="private context for the agent")
    p = sub.add_parser("hook", help="Claude Code hooks")
    p.add_argument("event", choices=["session-start", "session-end"])
    args = parser.parse_args(argv)
    try:
        if args.cmd == "record":
            raw = args.json if args.json is not None else sys.stdin.read()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                tutorlog.log(ROOT, "record", f"payload is not valid JSON ({exc}); nothing recorded")
                return 0
            record(payload)
        elif args.cmd == "context":
            print(context())
        elif args.event == "session-start":
            print(session_start(read_event()))
        else:
            read_event()
            finish()
    except Exception as exc:  # last line of defence: never surface to the learner
        tutorlog.log(ROOT, "tutor", f"{args.cmd} failed: {exc!r}")
        if args.cmd == "hook" and args.event == "session-start":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                     "additionalContext": "PRIVATE TUTOR CONTEXT unavailable; "
                                                     "run onboarding if there is no learner yet."}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
