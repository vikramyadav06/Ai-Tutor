#!/usr/bin/env python3
"""
Silent session log: append what happens while teaching to learner/sessions/<session_id>.jsonl.
Private to the learner's machine (learner/ is git-ignored). Nothing is sent anywhere.

    python tools/log_session.py start --subject <id> [--module <id>] [--agent claude-code]
    python tools/log_session.py step --module <id> --step-ref b1-s3 --type choice \
        --outcome correct [--attempts 1] [--hints 0] [--seconds 40 | --time-band "<30s"] \
        [--answer-text "..."]
    python tools/log_session.py move --topic <slug> --move analogy [--style examples] \
        [--worked true|false|unknown] [--note "..."]
    python tools/log_session.py signal --kind confused --topic <slug>
    python tools/log_session.py exercise --ref <slug> --passed true|false [--code-file path]
    python tools/log_session.py batch --module <id> --batch 2
    python tools/log_session.py feedback --rating 4 [--comment "..."]
    python tools/log_session.py end [--duration-min 35]
    python tools/log_session.py summary [--last 5]      # patterns across recent sessions

Every command except start/summary writes to the current session (learner/sessions/current)
or to --session <id>.
Commands print nothing, on success or failure, except `summary` (a query for the agent).
Failures go to learner/tutor.log and are retried next session; teaching continues.
Normally the agent doesn't call this directly: `tools/tutor.py record` does, once per batch.
Allowed values mirror TECH_SPEC §5 so Phase 2 can build shareable records from these logs.
Set TUTOR_ROOT to use another folder as the repo root (tests do this).
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
UUID_HEX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
AGENTS = ["claude-code", "codex", "cursor", "other"]
STEP_TYPES = ["learn", "choice", "fill", "order", "practice", "explain", "quiz", "free"]
OUTCOMES = ["correct", "incorrect", "skipped", "viewed"]
TIME_BANDS = ["<30s", "30s-2m", "2-5m", "5-15m", ">15m"]
MOVES = ["explanation", "analogy", "example", "worked-example", "visual", "re-explain", "question"]
STYLES = ["hands-on", "step-by-step", "examples", "analogies", "visual", "theory-first",
          "practice-questions", "discussion"]
WORKED = ["true", "false", "unknown"]
SIGNALS = ["confused", "confident", "bored", "frustrated", "asked-slower", "asked-faster", "took-break"]
LIMITS = {"answer_text": 500, "note": 300, "comment": 500}


class LogError(Exception):
    pass


def sessions_dir(root=None):
    return Path(root or ROOT) / "learner" / "sessions"


def now():
    return dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def parse_stamp(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)


def time_band(seconds):
    if seconds < 30:
        return "<30s"
    if seconds < 120:
        return "30s-2m"
    if seconds < 300:
        return "2-5m"
    if seconds < 900:
        return "5-15m"
    return ">15m"


def slug(name, value):
    if not isinstance(value, str) or not SLUG.match(value):
        raise LogError(f"{name} must be a slug (a-z, 0-9, -), got {value!r}")
    return value


def choice(name, value, allowed):
    if value not in allowed:
        raise LogError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def text(name, value):
    value = " ".join(str(value).split())
    if len(value) > LIMITS[name]:
        value = value[: LIMITS[name]]
    return value


def count(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000:
        raise LogError(f"{name} must be a whole number from 0 to 1000")
    return value


# ---------- session files ----------

def current_id(root=None):
    path = sessions_dir(root) / "current"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def session_path(session_id, root=None):
    if not UUID_HEX.match(session_id or ""):
        raise LogError(f"not a session id: {session_id!r}")
    return sessions_dir(root) / f"{session_id}.jsonl"


def read_events(session_id, root=None):
    path = session_path(session_id, root)
    if not path.exists():
        raise LogError(f"no session {session_id}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(session_id, event, root=None):
    path = session_path(session_id, root)
    if not path.exists():
        raise LogError(f"no session {session_id}; run start first")
    event = {"t": stamp(now()), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def resolve(session_id=None, root=None):
    sid = session_id or current_id(root)
    if not sid:
        raise LogError("no current session; run start first")
    return sid


def is_open(session_id, root=None):
    return not any(e["event"] == "end" for e in read_events(session_id, root))


# ---------- commands ----------

def start(subject, module=None, agent="other", root=None):
    slug("subject", subject)
    if module:
        slug("module", module)
    choice("agent", agent, AGENTS)
    previous = current_id(root)
    if previous and session_path(previous, root).exists() and is_open(previous, root):
        end(previous, auto=True, root=root)
    sid = str(uuid.uuid4())
    folder = sessions_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    event = {"t": stamp(now()), "event": "start", "session_id": sid, "subject": subject, "agent": agent}
    if module:
        event["module"] = module
    session_path(sid, root).write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
    (folder / "current").write_text(sid + "\n", encoding="utf-8")
    return sid


def step(module, step_ref, type_, outcome, attempts=1, hints=0, seconds=None, band=None,
         answer_text=None, session_id=None, root=None):
    if seconds is not None and band is not None:
        raise LogError("give --seconds or --time-band, not both")
    event = {
        "event": "step",
        "module": slug("module", module),
        "step_ref": slug("step_ref", step_ref),
        "type": choice("type", type_, STEP_TYPES),
        "outcome": choice("outcome", outcome, OUTCOMES),
        "attempts": count("attempts", attempts),
        "hints": count("hints", hints),
    }
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
            raise LogError("seconds must be a whole number of seconds")
        event["time_band"] = time_band(seconds)
    elif band is not None:
        event["time_band"] = choice("time_band", band, TIME_BANDS)
    if answer_text:
        event["answer_text"] = text("answer_text", answer_text)
    return append(resolve(session_id, root), event, root)


def move(topic, move_, style=None, worked="unknown", note=None, session_id=None, root=None):
    event = {"event": "move", "topic": slug("topic", topic), "move": choice("move", move_, MOVES),
             "worked": choice("worked", worked, WORKED)}
    if style:
        event["style"] = choice("style", style, STYLES)
    if note:
        event["note"] = text("note", note)
    return append(resolve(session_id, root), event, root)


def signal(kind, topic, session_id=None, root=None):
    event = {"event": "signal", "kind": choice("kind", kind, SIGNALS), "topic": slug("topic", topic)}
    return append(resolve(session_id, root), event, root)


def exercise(ref, passed, code_file=None, session_id=None, root=None):
    event = {"event": "exercise", "ref": slug("ref", ref), "passed": choice("passed", passed, ["true", "false"]) == "true"}
    if code_file:
        event["code_file"] = str(code_file)
    return append(resolve(session_id, root), event, root)


def batch(module, number, session_id=None, root=None):
    event = {"event": "batch", "module": slug("module", module), "batch": count("batch", number)}
    return append(resolve(session_id, root), event, root)


def feedback(rating, comment=None, session_id=None, root=None):
    if isinstance(rating, bool) or rating not in (1, 2, 3, 4, 5):
        raise LogError("rating must be 1-5")
    event = {"event": "feedback", "rating": rating}
    if comment:
        event["comment"] = text("comment", comment)
    return append(resolve(session_id, root), event, root)


def end(session_id=None, duration_min=None, auto=False, root=None):
    sid = resolve(session_id, root)
    events = read_events(sid, root)
    if any(e["event"] == "end" for e in events):
        raise LogError(f"session {sid} already ended")
    if duration_min is None:
        start_t = parse_stamp(events[0]["t"])
        last_t = parse_stamp(events[-1]["t"]) if auto else now()
        duration_min = max(0, int((last_t - start_t).total_seconds() // 60))
    event = {"event": "end", "duration_min": count("duration_min", duration_min)}
    if auto:
        event["auto_closed"] = True
    out = append(sid, event, root)
    cur = sessions_dir(root) / "current"
    if cur.exists() and cur.read_text(encoding="utf-8").strip() == sid:
        cur.unlink()
    return out


def summary(last=5, root=None):
    """Patterns across the most recent sessions, to adapt teaching (core/teaching/adaptation.md)."""
    folder = sessions_dir(root)
    sessions = []
    for path in folder.glob("*.jsonl") if folder.exists() else []:
        try:
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError:
            continue
        if events and events[0].get("event") == "start":
            sessions.append(events)
    sessions.sort(key=lambda ev: ev[0]["t"])
    sessions = sessions[-last:] if last else sessions

    steps = collections.Counter()
    wrong = collections.Counter()
    hinted = collections.Counter()
    signals = collections.Counter()
    moves = collections.defaultdict(lambda: collections.Counter())
    styles = collections.defaultdict(lambda: collections.Counter())
    slow = collections.Counter()
    minutes = 0
    for events in sessions:
        for e in events:
            kind = e.get("event")
            if kind == "step":
                steps[e["module"]] += 1
                if e["outcome"] == "incorrect" or e.get("attempts", 1) > 1:
                    wrong[e["module"]] += 1
                if e.get("hints", 0):
                    hinted[e["module"]] += 1
                if e.get("time_band") in ("5-15m", ">15m") and e["type"] not in ("practice", "explain"):
                    slow[e["module"]] += 1
            elif kind == "signal":
                signals[(e["kind"], e["topic"])] += 1
            elif kind == "move":
                moves[e["move"]][e["worked"]] += 1
                if e.get("style"):
                    styles[e["style"]][e["worked"]] += 1
            elif kind == "end":
                minutes += e.get("duration_min", 0)

    def rate(counter):
        tried = counter["true"] + counter["false"]
        return (counter["true"] / tried, tried) if tried else (None, 0)

    return {
        "sessions": len(sessions),
        "minutes": minutes,
        "steps": dict(steps),
        "struggled": {m: wrong[m] for m in steps if steps[m] and wrong[m] / steps[m] >= 0.3},
        "hints": dict(hinted),
        "slow_steps": dict(slow),
        "signals": {f"{k}:{t}": n for (k, t), n in signals.most_common()},
        "moves_that_work": sorted((m for m in moves if (rate(moves[m])[0] or 0) >= 0.6 and rate(moves[m])[1] >= 2),
                                  key=lambda m: -rate(moves[m])[0]),
        "moves_that_dont": sorted(m for m in moves if rate(moves[m])[0] is not None
                                  and rate(moves[m])[0] < 0.4 and rate(moves[m])[1] >= 2),
        "styles_that_work": sorted(s for s in styles if (rate(styles[s])[0] or 0) >= 0.6 and rate(styles[s])[1] >= 2),
    }


# ---------- command line ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def cmd(name, **kw):
        p = sub.add_parser(name, **kw)
        if name not in ("start", "summary"):
            p.add_argument("--session", help="session id (default: the current session)")
        return p

    p = cmd("start")
    p.add_argument("--subject", required=True)
    p.add_argument("--module")
    p.add_argument("--agent", default="other", choices=AGENTS)
    p = cmd("step")
    p.add_argument("--module", required=True)
    p.add_argument("--step-ref", required=True)
    p.add_argument("--type", required=True, choices=STEP_TYPES)
    p.add_argument("--outcome", required=True, choices=OUTCOMES)
    p.add_argument("--attempts", type=int, default=1)
    p.add_argument("--hints", type=int, default=0)
    p.add_argument("--seconds", type=int)
    p.add_argument("--time-band", choices=TIME_BANDS)
    p.add_argument("--answer-text")
    p = cmd("move")
    p.add_argument("--topic", required=True)
    p.add_argument("--move", required=True, choices=MOVES)
    p.add_argument("--style", choices=STYLES)
    p.add_argument("--worked", default="unknown", choices=WORKED)
    p.add_argument("--note")
    p = cmd("signal")
    p.add_argument("--kind", required=True, choices=SIGNALS)
    p.add_argument("--topic", required=True)
    p = cmd("exercise")
    p.add_argument("--ref", required=True)
    p.add_argument("--passed", required=True, choices=["true", "false"])
    p.add_argument("--code-file")
    p = cmd("batch")
    p.add_argument("--module", required=True)
    p.add_argument("--batch", type=int, required=True)
    p = cmd("feedback")
    p.add_argument("--rating", type=int, required=True)
    p.add_argument("--comment")
    p = cmd("end")
    p.add_argument("--duration-min", type=int)
    p = cmd("summary")
    p.add_argument("--last", type=int, default=5)
    args = parser.parse_args(argv)

    try:
        sid = getattr(args, "session", None)
        if args.cmd == "start":
            start(args.subject, args.module, args.agent)
        elif args.cmd == "step":
            step(args.module, args.step_ref, args.type, args.outcome, args.attempts, args.hints,
                 args.seconds, args.time_band, args.answer_text, session_id=sid)
        elif args.cmd == "move":
            move(args.topic, args.move, args.style, args.worked, args.note, session_id=sid)
        elif args.cmd == "signal":
            signal(args.kind, args.topic, session_id=sid)
        elif args.cmd == "exercise":
            exercise(args.ref, args.passed, args.code_file, session_id=sid)
        elif args.cmd == "batch":
            batch(args.module, args.batch, session_id=sid)
        elif args.cmd == "feedback":
            feedback(args.rating, args.comment, session_id=sid)
        elif args.cmd == "end":
            end(sid, args.duration_min)
        elif args.cmd == "summary":
            print(json.dumps(summary(args.last), indent=2))
    except Exception as exc:  # never interrupt teaching: log it, retry if that could help
        tutorlog.log(ROOT, "log_session", f"{args.cmd} failed: {exc}")
        if not isinstance(exc, LogError):
            tutorlog.queue(ROOT, "cli", {"tool": "log_session",
                                         "args": list(argv if argv is not None else sys.argv[1:])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
