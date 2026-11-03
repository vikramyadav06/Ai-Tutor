"""TECH_SPEC §14 Phase 2, with a test key pair generated here (never the owner's keys):
round-trip encrypt/decrypt, adult signature verifies, tampering fails, student records have no
linkable field (by schema and by searching the output), no PII after decryption."""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from nacl.exceptions import BadSignatureError, CryptoError
from nacl.public import PrivateKey, SealedBox
from nacl.signing import VerifyKey

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import collect  # noqa: E402
import learner  # noqa: E402
import log_session  # noqa: E402
import tutor  # noqa: E402

ADULT = {"name": "Arjun Mehta", "age_band": "25-34", "level": "professional", "explain_language": "en",
         "goals": ["Automate reports at work"], "preferred_styles": ["hands-on"], "pace": "steady"}
STUDENT = {"name": "Pinky", "age_band": "13-17", "level": "secondary", "explain_language": "en",
           "goals": ["Score well in the exam"], "preferred_styles": ["visual"]}
BATCH = {"subject": "python", "module": "first-steps", "agent": "claude-code",
         "steps": [{"step_ref": "b1-s1", "type": "learn", "outcome": "viewed", "seconds": 40},
                   {"step_ref": "b1-s2", "type": "choice", "outcome": "incorrect", "attempts": 2, "hints": 1},
                   {"step_ref": "b1-s3", "type": "explain", "outcome": "correct",
                    "answer_text": "Arjun here, mail me at arjun.m@example.com, a variable is a name for a value"}],
         "moves": [{"topic": "variables", "move": "analogy", "style": "examples", "worked": True,
                    "note": "Labelled boxes at Acme Logistics warehouse"}],
         "signals": [{"kind": "confused", "topic": "variables"}],
         "private_terms": ["Acme Logistics"],
         "feedback": {"rating": 5, "comment": "Thanks! I'm on 9876543210 if needed"},
         "end": True}


@pytest.fixture
def keypair():
    return PrivateKey.generate()  # test key, generated inside the test


@pytest.fixture
def config(keypair):
    return {"enabled": True, "data_branch": "tutor-data", "student_collection": False, "max_record_bytes": 262144,
            "keys": [{"key_id": "k1", "public_key_b64": base64.b64encode(bytes(keypair.public_key)).decode(),
                      "status": "active"}]}


def decrypt(path, keypair):
    return json.loads(SealedBox(keypair).decrypt(Path(path).read_bytes()))


def session(root, profile, sharing=True):
    learner.onboard(profile, root=root)
    learner.plan_subject("python", {}, root=root)
    learner.set_sharing(sharing, root)
    tutor.record({k: v for k, v in BATCH.items() if k != "end"}, root=root)
    log_session.end(root=root)  # (the real session end would collect with the repo's own config)


def schema(name):
    return json.loads((REPO / "core" / "schemas" / f"{name}.json").read_text())


def test_adult_round_trip_signed_and_scrubbed(tutor_root, keypair, config):
    session(tutor_root, ADULT)
    paths = collect.collect_pending(tutor_root, config)
    assert len(paths) == 1
    path = paths[0]
    assert re.search(r"\.tutor/outbox/k1/\d{4}-\d{2}-\d{2}/[0-9a-f]{32}\.bin$", path.as_posix())
    raw = path.read_bytes()
    assert b"first-steps" not in raw and b"lrn-" not in raw  # encrypted at rest

    env = decrypt(path, keypair)
    assert set(env) == {"v", "record", "pubkey", "sig", "scrub_version"} and env["v"] == 1
    assert env["scrub_version"].startswith("1.")
    record = env["record"]
    Draft202012Validator(schema("session.adult.v1")).validate(record)

    # signature verifies with the learner's key, and that key is the learner's identity
    VerifyKey(base64.b64decode(env["pubkey"])).verify(collect.canonical(record), base64.b64decode(env["sig"]))
    identity = json.loads((tutor_root / ".tutor" / "identity.json").read_text())
    seed_key = __import__("nacl.signing", fromlist=["SigningKey"]).SigningKey(base64.b64decode(identity["signing_seed_b64"]))
    assert env["pubkey"] == base64.b64encode(bytes(seed_key.verify_key)).decode()
    assert record["learner_id"] == identity["learner_id"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z", record["started_at"])

    # no PII after decryption
    text = json.dumps(env).lower()
    for pii in ("arjun", "mehta", "arjun.m@example.com", "acme logistics", "9876543210", "signing_seed"):
        assert pii not in text, pii
    assert "a variable is a name for a value" in record["steps"][2]["answer_text"]
    assert record["teaching_moves"][0]["worked"] is True


def test_tampering_fails(tutor_root, keypair, config):
    session(tutor_root, ADULT)
    path = collect.collect_pending(tutor_root, config)[0]
    env = decrypt(path, keypair)
    env["record"]["steps"][1]["outcome"] = "correct"  # change one answer
    with pytest.raises(BadSignatureError):
        VerifyKey(base64.b64decode(env["pubkey"])).verify(collect.canonical(env["record"]), base64.b64decode(env["sig"]))
    blob = bytearray(path.read_bytes())
    blob[60] ^= 0x01  # flip one bit of the ciphertext
    with pytest.raises(CryptoError):
        SealedBox(keypair).decrypt(bytes(blob))
    with pytest.raises(CryptoError):
        SealedBox(PrivateKey.generate()).decrypt(path.read_bytes())  # wrong key


LINKABLE = {"learner_id", "session_id", "started_at", "learner_model", "answer_text", "note", "code",
            "comment", "pubkey", "sig"}


def all_keys(schema_obj):
    keys = set()
    if isinstance(schema_obj, dict):
        keys |= set(schema_obj.get("properties", {}))
        for v in schema_obj.values():
            keys |= all_keys(v)
    elif isinstance(schema_obj, list):
        for v in schema_obj:
            keys |= all_keys(v)
    return keys


def test_student_schema_has_no_linkable_field():
    assert not all_keys(schema("session.student.v1")) & LINKABLE
    assert schema("session.student.v1")["properties"]["age_band"]["enum"] == ["under-13", "13-17"]


def test_student_record_carries_no_id(tutor_root, keypair, config):
    session(tutor_root, STUDENT)
    assert not (tutor_root / ".tutor" / "identity.json").exists()
    [path] = collect.collect_pending(tutor_root, config)
    env = decrypt(path, keypair)
    assert set(env) == {"v", "record", "scrub_version"}  # no key, no signature
    record = env["record"]
    Draft202012Validator(schema("session.student.v1")).validate(record)
    assert not all_keys({"properties": record}) & LINKABLE
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["date"])
    # search the whole output for anything linkable
    text = json.dumps(env)
    sid = json.loads(next((tutor_root / "learner" / "sessions").glob("*.jsonl")).read_text().splitlines()[0])["session_id"]
    for needle in (sid, "lrn-", "pinky", "Pinky", "arjun", "9876543210", "example.com", "Acme"):
        assert needle not in text, needle
    assert not re.search(r"T\d{2}:\d{2}", text)  # no time of day
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", text)  # no uuid of any kind


def test_two_student_records_cannot_be_linked(tutor_root, keypair, config):
    session(tutor_root, STUDENT)
    tutor.record({k: v for k, v in BATCH.items() if k != "end"}, root=tutor_root)
    log_session.end(root=tutor_root)
    paths = collect.collect_pending(tutor_root, config)
    assert len(paths) == 2
    a, b = (decrypt(p, keypair)["record"] for p in paths)
    assert a == b  # identical sessions give identical records: nothing unique to either


def test_nothing_built_without_consent(tutor_root, config):
    session(tutor_root, ADULT, sharing=False)
    assert collect.collect_pending(tutor_root, config) == []
    assert not (tutor_root / ".tutor" / "outbox").exists()
    learner.set_sharing(True, tutor_root)  # saying yes later never sends earlier sessions
    assert collect.collect_pending(tutor_root, config) == []
    state = json.loads((tutor_root / ".tutor" / "collected.json").read_text())
    assert list(state["sessions"].values()) == ["not-shared"]


def test_disabled_collector_builds_and_validates_but_writes_nothing(tutor_root, config):
    session(tutor_root, ADULT)
    assert collect.collect_pending(tutor_root, {**config, "enabled": False}) == []
    assert not (tutor_root / ".tutor" / "outbox").exists()
    state = json.loads((tutor_root / ".tutor" / "collected.json").read_text())
    assert list(state["sessions"].values()) == ["dry-run"]


def test_repo_project_json_keeps_collection_off():
    project = json.loads((REPO / "project.json").read_text())
    assert project["collector"]["enabled"] is False
    assert project["upstream_repo"] == "vikramwebgarh/Ai-Tutor"


def test_oversized_record_is_rejected(tutor_root, config):
    session(tutor_root, ADULT)
    assert collect.collect_pending(tutor_root, {**config, "max_record_bytes": 200}) == []
    assert "over max_record_bytes" in (tutor_root / "learner" / "tutor.log").read_text()


def test_unknown_fields_are_dropped():
    s = schema("session.student.v1")
    record = {"schema": "session.student.v1", "secret_field": "x",
              "steps": [{"module": "m", "step_ref": "b1-s1", "type": "learn", "outcome": "viewed",
                         "attempts": 1, "hints": 0, "answer_text": "would link"}]}
    out = collect.drop_unknown(record, s, s)
    assert "secret_field" not in out and "answer_text" not in out["steps"][0]


def test_every_schema_object_forbids_extra_fields():
    def walk(node, where):
        if isinstance(node, dict):
            if node.get("type") == "object":
                ok = node.get("additionalProperties") is False or where.endswith("files")
                assert ok, where
            for k, v in node.items():
                walk(v, f"{where}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}/{i}")
    for f in (REPO / "core" / "schemas").glob("*.json"):
        walk(json.loads(f.read_text()), f.name)


def test_newest_active_key_encrypts(tutor_root, config, keypair):
    k2 = PrivateKey.generate()
    config["keys"] = [{**config["keys"][0], "status": "retired"},
                      {"key_id": "k2", "public_key_b64": base64.b64encode(bytes(k2.public_key)).decode(),
                       "status": "active"}]
    session(tutor_root, ADULT)
    [path] = collect.collect_pending(tutor_root, config)
    assert "/outbox/k2/" in path.as_posix()
    decrypt(path, k2)
    with pytest.raises(collect.CollectError, match="not a valid public key"):
        collect.active_key({"keys": [{"key_id": "k1", "public_key_b64": "REPLACE_WITH_OWNER_PUBLIC_KEY",
                                      "status": "active"}]})


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def test_new_lessons_are_shared_unsigned_and_generic(tutor_root, keypair, config):
    git(tutor_root, "init", "-q")
    git(tutor_root, "add", "-A")
    git(tutor_root, "-c", "user.name=u", "-c", "user.email=u@invalid", "commit", "-q", "-m", "upstream content")
    session(tutor_root, ADULT)
    # the tutor writes a new lesson that (wrongly) mentions a private term
    new = tutor_root / "core" / "subjects" / "python" / "first-steps"
    new.mkdir(parents=True)
    lesson = json.loads((tutor_root / "core" / "subjects" / "class-9-science-exploration" / "chapter-01" / "lesson.json").read_text())
    lesson.update(id="first-steps", subject="python", planned_batches=None)
    lesson.pop("planned_batches")
    lesson["intro"] = "Written while teaching at Acme Logistics."
    (new / "lesson.json").write_text(json.dumps(lesson))
    # and starts another that isn't finished yet
    partial = tutor_root / "core" / "subjects" / "python" / "functions"
    partial.mkdir()
    (partial / "lesson.json").write_text(json.dumps({**lesson, "id": "functions", "planned_batches": ["a", "b", "c"]}))

    paths = collect.collect_pending(tutor_root, config)
    lessons = [e for e in (decrypt(p, keypair) for p in paths) if e["record"]["schema"] == "lesson.v1"]
    assert len(lessons) == 1  # not the unchanged upstream lessons, not the unfinished one
    env = lessons[0]
    assert set(env) == {"v", "record", "scrub_version"}
    record = env["record"]
    Draft202012Validator(schema("lesson.v1")).validate(record)
    assert record["module"] == "first-steps" and record["lesson"]["status"] == "unreviewed"
    text = json.dumps(record)
    assert "Acme" not in text and "lrn-" not in text and "Arjun" not in text
    # sent once only
    assert [p for p in collect.collect_pending(tutor_root, config)] == []


def test_delete_request_is_signed(tutor_root, keypair, config):
    learner.onboard(ADULT, root=tutor_root)
    path = collect.request_delete(tutor_root, config)
    env = decrypt(path, keypair)
    record = env["record"]
    Draft202012Validator(schema("delete.v1")).validate(record)
    VerifyKey(base64.b64decode(env["pubkey"])).verify(collect.canonical(record), base64.b64decode(env["sig"]))
    learner.onboard(STUDENT, root=tutor_root)
    with pytest.raises(collect.CollectError, match="only adults"):
        collect.request_delete(tutor_root, config)


def test_consent_samples_follow_the_mode():
    adult = json.loads(collect.consent_sample("adult"))
    student = json.loads(collect.consent_sample("student"))
    assert adult["schema"] == "session.adult.v1" and "learner_model" in adult
    assert student["schema"] == "session.student.v1"
    assert not all_keys({"properties": student}) & LINKABLE
    assert "answer_text" not in json.dumps(student) and "comment" not in json.dumps(student)


def test_delete_request_through_record(tutor_root, keypair, config):
    project = json.loads((tutor_root / "project.json").read_text())
    project["collector"] = config
    (tutor_root / "project.json").write_text(json.dumps(project))
    learner.onboard(ADULT, root=tutor_root)
    tutor.record({"delete_request": True}, root=tutor_root)  # no git repo here: stays in the outbox
    [path] = list((tutor_root / ".tutor" / "outbox").rglob("*.bin"))
    assert decrypt(path, keypair)["record"]["schema"] == "delete.v1"
