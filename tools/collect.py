#!/usr/bin/env python3
"""
Build shareable records, then scrub, validate, sign and encrypt them into .tutor/outbox/
(TECH_SPEC §5, §7). Runs invisibly at session end (tools/tutor.py finish); nothing here
talks to the network.

Order: build -> drop unknown fields -> scrub -> validate -> sign (adult) -> wrap -> encrypt.

    python tools/collect.py pending     # every finished session and new lesson not yet handled
    python tools/collect.py delete      # signed request to delete this adult's data

Nothing is built unless the learner said yes to sharing. Nothing is written to the outbox
unless collector.enabled is true in project.json (until then records are built and validated
only, as a dry run). Records are never printed or logged. Prints nothing; failures go to
learner/tutor.log. Set TUTOR_ROOT to use another folder as the repo root (tests do this).
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import learner  # noqa: E402
import log_session  # noqa: E402
import scrub  # noqa: E402
import tutorlog  # noqa: E402

ROOT = Path(os.environ.get("TUTOR_ROOT") or Path(__file__).resolve().parents[1])
SCHEMAS = {name: f"{name}.json" for name in ("session.adult.v1", "session.student.v1", "lesson.v1", "delete.v1",
                                             "subject.v1")}
SAFE_FILE_KEY = re.compile(r"^(exercises|solutions)/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$")
MAX_LESSON_FILES_BYTES = 50 * 1024
SAMPLE_SESSION = Path(__file__).resolve().parents[1] / "core" / "teaching" / "consent-sample-session.jsonl"


class CollectError(Exception):
    """A record that must not be sent (fails a check). Logged, never retried."""


# ---------- config and keys ----------

def load_config(root=None):
    project = json.loads((Path(root or ROOT) / "project.json").read_text(encoding="utf-8"))
    return project["collector"]


def active_key(config):
    """The newest active key: the last one with status 'active'."""
    keys = [k for k in config.get("keys", []) if k.get("status") == "active"]
    if not keys:
        raise CollectError("no active collector key in project.json")
    key = keys[-1]
    try:
        raw = base64.b64decode(key["public_key_b64"], validate=True)
    except (ValueError, base64.binascii.Error):
        raw = b""
    if len(raw) != 32:
        raise CollectError(f"collector key {key.get('key_id')} is not a valid public key yet")
    if not re.fullmatch(r"k\d+", key.get("key_id", "")):
        raise CollectError("collector key_id must look like k1, k2, ...")
    return key["key_id"], raw


# ---------- schema helpers ----------

def load_schema(name, root=None):
    return json.loads((Path(root or ROOT) / "core" / "schemas" / SCHEMAS[name]).read_text(encoding="utf-8"))


def _resolve(schema, root_schema):
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise CollectError(f"unsupported $ref {ref}")
        schema = root_schema["$defs"][ref.split("/")[-1]]
    return schema


def drop_unknown(value, schema, root_schema):
    """Keep only what the schema allows (TECH_SPEC §5: anything not in a schema is dropped)."""
    schema = _resolve(schema, root_schema)
    if isinstance(value, dict) and isinstance(schema, dict) and schema.get("type") == "object":
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", False)
        out = {}
        for k, v in value.items():
            if k in props:
                out[k] = drop_unknown(v, props[k], root_schema)
            elif isinstance(extra, dict):
                out[k] = drop_unknown(v, extra, root_schema)
        return out
    if isinstance(value, list) and isinstance(schema, dict) and "items" in schema:
        return [drop_unknown(v, schema["items"], root_schema) for v in value]
    return value


def validate(record, schema):
    from jsonschema import Draft202012Validator
    errors = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(record)"
        # the message may quote record content; keep only the location and the rule that failed
        raise CollectError(f"schema check failed at {where} ({first.validator})")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def private_terms(root=None):
    data = learner.read_json(learner.learner_dir(root) / "private_terms.json", {"terms": []})
    return data.get("terms", [])


def prepare(record, schema_name, root=None, terms=None):
    """drop unknown -> scrub every string -> validate. Returns the clean record."""
    schema = load_schema(schema_name, root)
    record = drop_unknown(record, schema, schema)
    record, _ = scrub.scrub_record(record, private_terms(root) if terms is None else terms)
    validate(record, schema)
    return record


# ---------- building records ----------

def _topics(events):
    seen = []
    for e in events:
        for key in ("module", "topic"):
            value = e.get(key)
            if e.get("event") in ("step", "move", "signal") and value and value not in seen:
                seen.append(value)
    return seen[:50]


def _read_code(code_file, root):
    """Exercise code, only from the learner's my-work/ folder."""
    if not code_file:
        return None
    base = (Path(root) / "my-work").resolve()
    path = (Path(root) / code_file).resolve()
    if base not in path.parents or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:20000]


def textbook_fields(subject, root=None):
    """board (a category) and textbook_edition (a slug) for school and college subjects, from
    the learner's subject answers. Never an institution's name."""
    answers = learner.read_json(learner.subject_dir(subject, root) / "answers.json", {}) if subject else {}
    out = {}
    board = answers.get("board")
    if board in learner.BOARDS:
        out["board"] = board
    book = " ".join(x for x in (answers.get("textbook"), answers.get("edition")) if x)
    if book and board not in ("university", "other"):
        cleaned, findings = scrub.scrub_text(book, private_terms(root))
        slug = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")[:63].strip("-")
        if not findings and slug:
            out["textbook_edition"] = slug
    return out


def build_session_record(events, profile, model, root=None, identity=None):
    """Turn a local session log into the record for the learner's mode."""
    root = Path(root or ROOT)
    start = events[0]
    end = next((e for e in events if e.get("event") == "end"), {})
    adult = profile.get("mode") == "adult"
    steps, moves, signals, exercises, feedback = [], [], [], [], None
    for e in events:
        kind = e.get("event")
        if kind == "step":
            step = {k: e[k] for k in ("module", "step_ref", "type", "outcome", "attempts", "hints", "time_band") if k in e}
            if adult and e.get("answer_text"):
                step["answer_text"] = e["answer_text"]
            steps.append(step)
        elif kind == "move":
            move = {"topic": e["topic"], "move": e["move"],
                    "worked": {"true": True, "false": False}.get(e.get("worked"), "unknown")}
            if e.get("style"):
                move["style"] = e["style"]
            if adult and e.get("note"):
                move["note"] = e["note"]
            moves.append(move)
        elif kind == "signal":
            signals.append({"kind": e["kind"], "topic": e["topic"]})
        elif kind == "exercise":
            ex = {"ref": e["ref"], "passed": bool(e.get("passed"))}
            code = _read_code(e.get("code_file"), root) if adult else None
            if code:
                ex["code"] = code
            exercises.append(ex)
        elif kind == "feedback":
            feedback = {"rating": e["rating"]}
            if adult and e.get("comment"):
                feedback["comment"] = e["comment"]
    record = {
        "duration_min": end.get("duration_min", 0),
        "agent": start.get("agent", "other"),
        "explain_language": profile.get("explain_language", "en"),
        "subject": start.get("subject"),
        **textbook_fields(start.get("subject"), root),
        "topics": _topics(events),
        "level": profile.get("level"),
        "age_band": profile.get("age_band"),
        "steps": steps,
        "teaching_moves": moves,
        "signals": signals,
        "exercises": exercises,
    }
    if feedback:
        record["feedback"] = feedback
    if adult:
        if not identity:
            raise CollectError("adult record without an identity")
        record = {"schema": "session.adult.v1", "learner_id": identity["learner_id"],
                  "session_id": start["session_id"], "started_at": start["t"],
                  "learner_model": {k: model.get(k, [] if k not in ("journey_stage", "pace") else None)
                                    for k in ("goals", "journey_stage", "preferred_styles", "pace",
                                              "strengths", "weak_areas", "what_works")},
                  **record}
        return "session.adult.v1", record
    return "session.student.v1", {"schema": "session.student.v1", "date": start["t"][:10], **record}


def build_lesson_record(lesson_path, root=None):
    lesson_path = Path(lesson_path)
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    lesson["status"] = "unreviewed"  # whatever the tutor wrote is a proposal until Repo B reviews it
    files, total = {}, 0
    for sub in ("exercises", "solutions"):
        for f in sorted((lesson_path.parent / sub).glob("*")):
            if f.is_file() and not f.is_symlink() and f.suffix in (".py", ".md", ".txt", ".json", ".csv"):
                text = f.read_text(encoding="utf-8", errors="replace")
                total += len(text.encode())
                if total > MAX_LESSON_FILES_BYTES:
                    raise CollectError(f"lesson files over {MAX_LESSON_FILES_BYTES // 1024} KB")
                files[f"{sub}/{f.name}"] = text
    check_file_keys(files)
    return "lesson.v1", {"schema": "lesson.v1", "subject": lesson.get("subject"), "module": lesson.get("id"),
                         "level": lesson.get("level"), "explain_language": lesson.get("explain_language"),
                         "lesson": lesson, "files": files}


def check_file_keys(files):
    """Lesson file paths must stay inside the module folder (the schema checks this too)."""
    for key in files:
        if (not isinstance(key, str) or ".." in key or "\\" in key or key.startswith("/")
                or re.match(r"^[A-Za-z]:", key) or not SAFE_FILE_KEY.match(key)):
            raise CollectError(f"unsafe lesson file path {key!r}")


def build_subject_record(catalog_path):
    """A subject's chapter list from a learner's own book: no learner data, never signed."""
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    syllabus = catalog.get("syllabus") or {}
    if syllabus.get("provisional"):
        raise CollectError("provisional catalog (not from the learner's book); not shared")
    record = {"schema": "subject.v1", "subject": catalog.get("subject"), "title": catalog.get("title"),
              "level": (catalog.get("levels") or [None])[0], "explain_language": catalog.get("explain_language", "en"),
              "status": "unreviewed",
              "chapters": [{k: m[k] for k in ("id", "title", "kind") if k in m}
                           | ({"number": m["chapter"]} if "chapter" in m else {}) for m in catalog.get("modules", [])]}
    if syllabus.get("board") in learner.BOARDS:
        record["board"] = syllabus["board"]
    if syllabus.get("board") not in ("university", "other"):
        for key in ("textbook", "edition"):
            if syllabus.get(key):
                record[key] = syllabus[key]
    return "subject.v1", record


# ---------- signing, wrapping, encrypting ----------

def envelope(record, identity=None):
    env = {"v": 1, "record": record, "scrub_version": scrub.SCRUB_VERSION}
    if identity:
        from nacl.signing import SigningKey
        key = SigningKey(base64.b64decode(identity["signing_seed_b64"]))
        env["sig"] = base64.b64encode(key.sign(canonical(record)).signature).decode()
        env["pubkey"] = base64.b64encode(bytes(key.verify_key)).decode()
    return env


def seal(record, identity, config, root=None, day=None, write=True):
    """Wrap, size-check, encrypt and (if write) save to the outbox. Returns the path or None."""
    data = canonical(envelope(record, identity))
    if len(data) > config.get("max_record_bytes", 262144):
        raise CollectError(f"record is {len(data)} bytes, over max_record_bytes")
    if not write:
        return None
    from nacl.public import PublicKey, SealedBox
    key_id, public = active_key(config)
    sealed = SealedBox(PublicKey(public)).encrypt(data)
    day = day or dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = learner.tutor_dir(root) / "outbox" / key_id / day / f"{uuid.uuid4().hex}.bin"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sealed)
    return out


# ---------- what has been handled ----------

def _state_path(root):
    return learner.tutor_dir(root) / "collected.json"


def load_state(root=None):
    return learner.read_json(_state_path(root), {"sessions": {}, "lessons": {}})


def save_state(state, root=None):
    learner.write_private_json(_state_path(root), state)


def finished_sessions(root=None):
    folder = log_session.sessions_dir(root)
    for path in sorted(folder.glob("*.jsonl")) if folder.exists() else []:
        try:
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError:
            continue
        if events and events[0].get("event") == "start" and any(e.get("event") == "end" for e in events):
            yield events[0]["session_id"], events


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)


def written_here(root, path):
    """True if this file was written or changed on this machine by the tutor: untracked,
    modified, or only ever committed by the tutor's own session-end commits."""
    rel = Path(path).relative_to(root).as_posix()
    status = _git(root, "status", "--porcelain", "--", rel).stdout.strip()
    subjects = set(_git(root, "log", "--format=%s", "--", rel).stdout.split("\n")) - {""}
    return bool(status) or bool(subjects and subjects <= {"tutor: save work and lessons"})


def new_lessons(root=None):
    """Lessons written here (see written_here). Complete ones only (all planned batches)."""
    root = Path(root or ROOT)
    if not (root / ".git").exists():
        return []
    out = []
    for path in sorted((root / "core" / "subjects").glob("*/*/lesson.json")):
        try:
            lesson = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        planned = lesson.get("planned_batches")
        if planned and len(lesson.get("batches", [])) < len(planned):
            continue  # still being written
        if written_here(root, path):
            out.append(path)
    return out


def new_catalogs(root=None):
    """Subject catalogs written here from a learner's book (not provisional ones)."""
    root = Path(root or ROOT)
    if not (root / ".git").exists():
        return []
    return [p for p in sorted((root / "core" / "subjects").glob("*/catalog.json")) if written_here(root, p)]


# ---------- the collector ----------

def collect_pending(root=None, config=None):
    """Handle every finished session and new lesson once. Returns the outbox paths written."""
    root = Path(root or ROOT)
    profile = learner.read_json(learner.learner_dir(root) / "profile.json")
    if not profile:
        return []
    config = config or load_config(root)
    sharing = bool(profile.get("sharing"))
    write = bool(config.get("enabled")) and sharing
    state = load_state(root)
    written = []
    adult = profile.get("mode") == "adult"
    identity = learner.read_json(learner.identity_path(root)) if adult else None
    model = learner.read_json(learner.learner_dir(root) / "model.json", {})

    if config.get("student_collection"):
        tutorlog.log(root, "collect", "WARNING: student_collection is true in project.json, but no linked "
                                      "student schema exists; students' sessions stay anonymous and unlinked")

    for sid, events in finished_sessions(root):
        if sid in state["sessions"]:
            continue
        if not sharing:
            state["sessions"][sid] = "not-shared"  # never sent later, even if sharing is turned on
            continue
        if not config.get("enabled"):
            outcome = "dry-run"
        else:
            outcome = "sent"
        try:
            name, record = build_session_record(events, profile, model, root, identity)
            if not record["steps"] and not record["teaching_moves"]:
                state["sessions"][sid] = "empty"
                continue
            record = prepare(record, name, root)
            path = seal(record, identity if adult else None, config, root,
                        day=events[0]["t"][:10], write=write)
            if path:
                written.append(path)
            state["sessions"][sid] = outcome
        except CollectError as exc:
            tutorlog.log(root, "collect", f"session not shared: {exc}")
            state["sessions"][sid] = "rejected"

    if sharing:
        for path in new_catalogs(root):
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if state["lessons"].get(rel) == digest:
                continue
            try:
                name, record = build_subject_record(path)
                record = prepare(record, name, root)
                out = seal(record, None, config, root, write=write)  # never signed
                if out:
                    written.append(out)
                state["lessons"][rel] = digest
            except CollectError as exc:
                tutorlog.log(root, "collect", f"subject {rel} not shared: {exc}")
                if "provisional" not in str(exc):
                    state["lessons"][rel] = digest  # a provisional one is shared once it's from the book
        for path in new_lessons(root):
            rel = path.relative_to(root).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if state["lessons"].get(rel) == digest:
                continue
            try:
                name, record = build_lesson_record(path, root)
                record = prepare(record, name, root)
                out = seal(record, None, config, root, write=write)  # lessons are never signed
                if out:
                    written.append(out)
                state["lessons"][rel] = digest
            except CollectError as exc:
                tutorlog.log(root, "collect", f"lesson {rel} not shared: {exc}")
                state["lessons"][rel] = digest
    save_state(state, root)
    return written


def request_delete(root=None, config=None):
    """Signed delete.v1 request for this adult learner (TECH_SPEC §5.4)."""
    root = Path(root or ROOT)
    config = config or load_config(root)
    identity = learner.read_json(learner.identity_path(root))
    if not identity:
        raise CollectError("only adults with a learner id can request deletion")
    record = prepare({"schema": "delete.v1", "learner_id": identity["learner_id"],
                      "requested_at": dt.datetime.now(dt.timezone.utc).date().isoformat()}, "delete.v1", root, terms=[])
    if not config.get("enabled"):
        raise CollectError("data collection is not switched on; nothing to delete")
    return seal(record, identity, config, root)


def consent_sample(mode):
    """The example record shown with the consent question: built from an invented sample
    session through the same pipeline, never from the learner's data."""
    events = [json.loads(line) for line in SAMPLE_SESSION.read_text(encoding="utf-8").splitlines() if line.strip()]
    sample_profile = {"mode": mode, "explain_language": "en", "level": "college" if mode == "adult" else "secondary",
                      "age_band": "18-24" if mode == "adult" else "13-17"}
    sample_model = {"goals": ["Write small programs to automate everyday tasks"], "journey_stage": "beginner",
                    "preferred_styles": ["examples", "hands-on"], "pace": "steady",
                    "strengths": ["variables"], "weak_areas": ["return-values"],
                    "what_works": ["a real-life example before the code"]}
    identity = {"learner_id": "lrn-abcd2345"}
    name, record = build_session_record(events, sample_profile, sample_model, identity=identity)
    root = Path(__file__).resolve().parents[1]
    record = prepare(record, name, root, terms=[])
    return json.dumps(record, indent=2, ensure_ascii=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    sub.add_parser("delete")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "pending":
            collect_pending()
        else:
            request_delete()
    except Exception as exc:
        tutorlog.log(ROOT, "collect", f"{args.cmd} failed: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
