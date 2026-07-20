"""Tests for the telemetry sink."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.telemetry import Telemetry


@pytest.fixture()
def tel(tmp_path) -> Telemetry:
    return Telemetry(sink=tmp_path / "telemetry.jsonl")


def _read_events(tel: Telemetry) -> list[dict]:
    sink: Path = tel._sinks[0]  # type: ignore[attr-defined]
    if not sink.exists():
        return []
    return [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]


# ── Session and request IDs ───────────────────────────────────────────────────

def test_session_id_is_stable_within_instance(tel):
    assert tel.session_id == tel.session_id


def test_two_instances_have_different_session_ids(tmp_path):
    # session_id is session-<unix_ms> (mirrors the Rust implementation's
    # convention), so instances created within the same millisecond can
    # collide by design — space them out to assert real uniqueness.
    import time
    t1 = Telemetry(sink=tmp_path / "a.jsonl")
    time.sleep(0.002)
    t2 = Telemetry(sink=tmp_path / "b.jsonl")
    assert t1.session_id != t2.session_id


def test_request_id_is_unique_each_call(tel):
    ids = {tel.new_request_id() for _ in range(50)}
    assert len(ids) == 50


# ── Event writing ─────────────────────────────────────────────────────────────

def test_emit_writes_one_json_line(tel):
    tel.emit("app.start")
    events = _read_events(tel)
    assert len(events) == 1
    assert events[0]["event"] == "app.start"


def test_emit_includes_session_id(tel):
    tel.emit("app.start")
    event = _read_events(tel)[0]
    assert event["session_id"] == tel.session_id


def test_emit_fields_are_present(tel):
    rid = tel.new_request_id()
    tel.emit(
        "tts.synthesis_start",
        request_id=rid,
        engine="sapi5",
        model="",
        voice="en-US",
        text_chars=42,
        text_bytes=42,
        latency_ms=0,
    )
    e = _read_events(tel)[0]
    assert e["request_id"] == rid
    assert e["engine"] == "sapi5"
    assert e["text_chars"] == 42
    assert e["timestamp_unix_ms"] > 0


def test_emit_multiple_events_appends(tel):
    for evt in ("app.start", "speak.triggered", "tts.synthesis_start"):
        tel.emit(evt)
    events = _read_events(tel)
    assert len(events) == 3
    assert [e["event"] for e in events] == [
        "app.start", "speak.triggered", "tts.synthesis_start"
    ]


def test_emit_status_error_with_detail(tel):
    tel.emit("tts.error", status="error", detail="something went wrong")
    e = _read_events(tel)[0]
    assert e["status"] == "error"
    assert e["detail"] == "something went wrong"


def test_emit_does_not_raise_on_unwritable_sink(tmp_path):
    # Sink is a directory (cannot write a file there)
    bad_sink = tmp_path / "is_a_dir"
    bad_sink.mkdir()
    t = Telemetry(sink=bad_sink)
    t.emit("app.start")  # must not raise


def test_emit_does_not_include_source_text(tel):
    tel.emit("speak.triggered", text_chars=10, text_bytes=10)
    e = _read_events(tel)[0]
    for key in e:
        assert "text" not in key.lower() or key in ("text_chars", "text_bytes"), \
            f"Unexpected text-related key: {key}"
    # Confirm no raw text value
    for v in e.values():
        if isinstance(v, str):
            assert len(v) < 100 or not v[0].isalpha()


def test_config_changed_event(tel):
    tel.emit("config.changed", engine="sapi5", detail="voice")
    e = _read_events(tel)[0]
    assert e["event"] == "config.changed"
    assert e["detail"] == "voice"
