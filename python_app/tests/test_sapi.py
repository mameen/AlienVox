"""Tests for the SAPI5 engine — runs only on Windows with SAPI installed.

speak_to_wav() renders to a file so no speakers/audio device are required.
Voice IDs are tested to be stable registry paths, not volatile indices.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only"
)


@pytest.fixture(scope="module")
def engine():
    from src.engines.sapi_win import SapiEngine
    return SapiEngine()


@pytest.fixture(scope="module")
def first_voice(engine):
    voices = engine.list_voices()
    assert voices, "No SAPI voices installed — test environment incomplete"
    return voices[0]


# ── Voice enumeration ─────────────────────────────────────────────────────────

def test_list_voices_returns_at_least_one(engine):
    voices = engine.list_voices()
    assert len(voices) >= 1


def test_voices_have_non_empty_ids(engine):
    for v in engine.list_voices():
        assert v.id, f"Voice {v.name!r} has empty id"


def test_voices_have_non_empty_names(engine):
    for v in engine.list_voices():
        assert v.name, f"Voice id {v.id!r} has empty name"


def test_voice_ids_are_registry_paths(engine):
    """IDs must be stable HKEY_ registry paths, not integer indices."""
    for v in engine.list_voices():
        assert "HKEY_" in v.id or "HKLM" in v.id or "Tokens" in v.id, (
            f"Voice ID {v.id!r} does not look like a registry path"
        )


def test_voice_ids_are_unique(engine):
    ids = [v.id for v in engine.list_voices()]
    assert len(ids) == len(set(ids)), "Duplicate voice IDs detected"


# ── speak_to_wav ──────────────────────────────────────────────────────────────

def test_speak_to_wav_creates_file(engine, first_voice, tmp_path):
    from src.engines.base import SpeakParams
    out = tmp_path / "out.wav"
    engine.speak_to_wav("Hello AlienVox", first_voice.id, SpeakParams(), out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_speak_to_wav_is_valid_wav(engine, first_voice, tmp_path):
    from src.engines.base import SpeakParams
    out = tmp_path / "valid.wav"
    engine.speak_to_wav("test", first_voice.id, SpeakParams(), out)
    with wave.open(str(out)) as wf:
        assert wf.getnframes() > 0
        assert wf.getnchannels() in (1, 2)
        assert wf.getframerate() > 0


def test_speak_to_wav_rate_applied(engine, first_voice, tmp_path):
    from src.engines.base import SpeakParams
    # Different rates should produce different durations
    slow = tmp_path / "slow.wav"
    fast = tmp_path / "fast.wav"
    engine.speak_to_wav("the quick brown fox", first_voice.id, SpeakParams(rate=-5), slow)
    engine.speak_to_wav("the quick brown fox", first_voice.id, SpeakParams(rate=5), fast)
    with wave.open(str(slow)) as sw, wave.open(str(fast)) as fw:
        assert sw.getnframes() > fw.getnframes(), "Slow rate should produce more frames"


def test_speak_to_wav_respects_voice_id(engine, tmp_path):
    """Each voice listed produces output — confirms ID lookup works."""
    from src.engines.base import SpeakParams
    voices = engine.list_voices()
    for v in voices[:2]:  # test first two to keep runtime reasonable
        out = tmp_path / f"{v.id.split(chr(92))[-1]}.wav"
        engine.speak_to_wav("hi", v.id, SpeakParams(), out)
        assert out.stat().st_size > 0, f"No output for voice {v.name!r}"


# ── stop / pause / resume ─────────────────────────────────────────────────────

def test_stop_does_not_raise(engine):
    engine.stop()


def test_pause_resume_does_not_raise(engine):
    engine.pause()
    engine.resume()
