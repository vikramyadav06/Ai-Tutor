"""tools/log_session.py: silent, local, with TECH_SPEC §5 values only."""
import json
import re

import pytest


def events(root, sid):
    path = root / "learner" / "sessions" / f"{sid}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_full_session_via_cli(tutor_root, run_tool):
    sid = run_tool("log_session", "start", "--subject", "class-9-science", "--module", "matter",
                   "--agent", "claude-code").stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", sid)
    quiet = [
        ("step", "--module", "matter", "--step-ref", "b1-s2", "--type", "choice", "--outcome", "incorrect",
         "--attempts", "2", "--hints", "1", "--seconds", "75"),
        ("move", "--topic", "states-of-matter", "--move", "analogy", "--style", "analogies", "--worked", "true",
         "--note", "Compared particles to people in a crowd"),
        ("signal", "--kind", "confused", "--topic", "latent-heat"),
        ("exercise", "--ref", "melting-ice", "--passed", "true"),
        ("batch", "--module", "matter", "--batch", "1"),
        ("feedback", "--rating", "5", "--comment", "Clear"),
        ("end", "--duration-min", "25"),
    ]
    for args in quiet:
        result = run_tool("log_session", *args)
        assert result.stdout == "" and result.stderr == ""  # silent

    ev = events(tutor_root, sid)
    assert [e["event"] for e in ev] == ["start", "step", "move", "signal", "exercise", "batch", "feedback", "end"]
    assert ev[0]["subject"] == "class-9-science" and ev[0]["agent"] == "claude-code"
    assert ev[1]["time_band"] == "30s-2m" and ev[1]["attempts"] == 2 and ev[1]["hints"] == 1
    assert ev[4]["passed"] is True
    assert ev[-1]["duration_min"] == 25
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z", e["t"]) for e in ev)  # minute precision, UTC
    assert not (tutor_root / "learner" / "sessions" / "current").exists()


@pytest.mark.parametrize("seconds,band", [(0, "<30s"), (29, "<30s"), (30, "30s-2m"), (119, "30s-2m"),
                                          (120, "2-5m"), (299, "2-5m"), (300, "5-15m"), (899, "5-15m"),
                                          (900, ">15m"), (5000, ">15m")])
def test_time_bands(log_tool, seconds, band):
    assert log_tool.time_band(seconds) == band


@pytest.mark.parametrize("call,message", [
    (lambda lt, r: lt.step("matter", "b1-s1", "choice", "maybe", root=r), "outcome must be one of"),
    (lambda lt, r: lt.step("Matter Module", "b1-s1", "choice", "correct", root=r), "module must be a slug"),
    (lambda lt, r: lt.step("matter", "b1-s1", "essay", "correct", root=r), "type must be one of"),
    (lambda lt, r: lt.step("matter", "b1-s1", "choice", "correct", seconds=5, band="<30s", root=r), "not both"),
    (lambda lt, r: lt.move("matter", "hypnosis", root=r), "move must be one of"),
    (lambda lt, r: lt.signal("sleepy", "matter", root=r), "kind must be one of"),
    (lambda lt, r: lt.feedback(6, root=r), "rating must be 1-5"),
])
def test_unknown_values_are_rejected(tutor_root, log_tool, call, message):
    log_tool.start("class-9-science", root=tutor_root)
    with pytest.raises(log_tool.LogError, match=message):
        call(log_tool, tutor_root)


def test_no_session_yet(tutor_root, log_tool, run_tool):
    with pytest.raises(log_tool.LogError, match="no current session"):
        log_tool.step("matter", "b1-s1", "learn", "viewed", root=tutor_root)
    result = run_tool("log_session", "end", check=False)
    assert result.returncode == 2 and "error:" in result.stderr


def test_session_id_cannot_escape_folder(tutor_root, log_tool):
    with pytest.raises(log_tool.LogError, match="not a session id"):
        log_tool.end(session_id="../../profile", root=tutor_root)


def test_long_text_is_trimmed(tutor_root, log_tool):
    sid = log_tool.start("python", root=tutor_root)
    log_tool.step("functions", "b1-s1", "explain", "correct", answer_text="word " * 400, root=tutor_root)
    log_tool.move("functions", "example", note="n" * 1000, root=tutor_root)
    ev = events(tutor_root, sid)
    assert len(ev[1]["answer_text"]) == 500
    assert len(ev[2]["note"]) == 300


def test_new_start_closes_open_session(tutor_root, log_tool):
    first = log_tool.start("python", root=tutor_root)
    second = log_tool.start("python", root=tutor_root)
    assert events(tutor_root, first)[-1]["event"] == "end"
    assert events(tutor_root, first)[-1]["auto_closed"] is True
    assert (tutor_root / "learner" / "sessions" / "current").read_text().strip() == second
    with pytest.raises(log_tool.LogError, match="already ended"):
        log_tool.end(session_id=first, root=tutor_root)


def test_summary_finds_patterns_for_adaptation(tutor_root, log_tool, run_tool):
    lt, r = log_tool, tutor_root
    for _ in range(3):
        lt.start("class-9-science", root=r)
        lt.step("matter", "b1-s2", "choice", "incorrect", attempts=2, hints=1, root=r)
        lt.step("matter", "b1-s4", "fill", "correct", root=r)
        lt.step("motion", "b1-s2", "choice", "correct", band="5-15m", root=r)
        lt.move("states-of-matter", "analogy", style="analogies", worked="true", root=r)
        lt.move("states-of-matter", "explanation", style="theory-first", worked="false", root=r)
        lt.signal("confused", "latent-heat", root=r)
        lt.end(duration_min=20, root=r)

    s = lt.summary(last=5, root=r)
    assert s["sessions"] == 3 and s["minutes"] == 60
    assert s["struggled"] == {"matter": 3}  # 3 of 6 matter steps went wrong
    assert "motion" not in s["struggled"]
    assert s["hints"] == {"matter": 3}
    assert s["slow_steps"] == {"motion": 3}
    assert s["signals"] == {"confused:latent-heat": 3}
    assert s["moves_that_work"] == ["analogy"]
    assert s["moves_that_dont"] == ["explanation"]
    assert s["styles_that_work"] == ["analogies"]
    assert lt.summary(last=1, root=r)["sessions"] == 1

    out = json.loads(run_tool("log_session", "summary").stdout)
    assert out["moves_that_work"] == ["analogy"]


def test_summary_with_no_sessions(tutor_root, log_tool):
    assert log_tool.summary(root=tutor_root)["sessions"] == 0
