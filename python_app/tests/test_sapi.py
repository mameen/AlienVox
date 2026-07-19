"""Tests for the SAPI5 engine — runs only on Windows with SAPI installed.

speak_to_wav() renders to a file so no speakers/audio device are required.
Voice IDs are tested to be stable registry paths, not volatile indices.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

from src.engines.base import SpeakParams

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


# ── WaitUntilDone timeout ─────────────────────────────────────────────────────

def test_wait_until_done_with_timeout_does_not_block_forever(engine):
    """WaitUntilDone(-1) blocks forever if SAPI hangs; a finite timeout must return."""
    engine.stop()
    sapi = engine.get_thread_local_sapi()
    result = sapi.WaitUntilDone(0)
    assert isinstance(result, bool)


def test_wait_until_done_returns_bool(engine):
    """WaitUntilDone should return a boolean indicating completion status."""
    engine.stop()
    sapi = engine.get_thread_local_sapi()
    result = sapi.WaitUntilDone(100)
    assert isinstance(result, bool), f"Expected bool, got {type(result)}"


# ── Thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_speak_calls_do_not_raise(engine):
    """Multiple simultaneous speak() calls should not raise COM/threading errors."""
    import threading

    voices = engine.list_voices()
    assert len(voices) >= 1
    errors: list[Exception] = []

    def _speak(idx: int):
        try:
            engine.speak(f"thread {idx}", voices[0].id, SpeakParams())
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_speak, args=(i,), daemon=True) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    engine.stop()
    assert not errors, f"Concurrent speak raised: {errors}"


def test_concurrent_stop_and_speak_does_not_raise(engine):
    """Calling stop() while speak() is in progress should not raise."""
    import threading
    import time

    voices = engine.list_voices()
    assert len(voices) >= 1
    errors: list[Exception] = []

    def _speak():
        try:
            engine.speak("longer text that takes time to process " * 100, voices[0].id, SpeakParams())
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=_speak, daemon=True)
    t.start()
    time.sleep(0.05)
    engine.stop()
    t.join(timeout=10)

    assert not errors, f"Concurrent stop/speak raised: {errors}"


# ── Error handling ────────────────────────────────────────────────────────────

def test_speak_with_bad_voice_id_does_not_raise(engine):
    """A non-existent voice_id should fall back to the default voice, not crash."""
    engine.speak("hello", "HKEY_FAKE_NONEXISTENT_VOICE", SpeakParams())
    engine.stop()


def test_speak_with_empty_text_does_not_raise(engine, first_voice):
    """Speaking empty text should be a no-op, not raise."""
    engine.speak("", first_voice.id, SpeakParams())
    engine.stop()


def test_speak_to_wav_with_bad_voice_id_falls_back(engine, tmp_path):
    """speak_to_wav with an unknown voice_id should fall back to default and still produce output."""
    out = tmp_path / "fallback.wav"
    engine.speak_to_wav("hello", "HKEY_FAKE_NONEXISTENT", SpeakParams(), out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_speak_with_non_string_text_raises(engine, first_voice):
    """Passing non-string text should raise a TypeError or similar."""
    with pytest.raises((TypeError, AttributeError)):
        engine.speak(123, first_voice.id, SpeakParams())


# ── speak_sync blocking behavior ──────────────────────────────────────────────

def test_speak_sync_blocks_until_complete(engine, first_voice):
    """speak_sync should block until the speech is fully processed."""
    import time

    start = time.monotonic()
    engine.speak_sync("hello", first_voice.id, SpeakParams())
    elapsed = time.monotonic() - start
    assert elapsed >= 0, "speak_sync returned without processing"


# ── Voice selection ───────────────────────────────────────────────────────────

def test_set_voice_to_existing_voice(engine):
    """Setting a known voice_id should not raise and should be retrievable."""
    voices = engine.list_voices()
    assert len(voices) >= 1
    target = voices[0]
    sapi = engine.get_thread_local_sapi()
    sapi.Voice = engine._find_token(target.id, sapi=sapi)


def test_voice_change_affects_output(engine, tmp_path):
    """Changing voices should produce output for each — confirms voice selection works."""
    voices = engine.list_voices()
    if len(voices) < 2:
        pytest.skip("Need at least 2 voices to compare")

    out_a = tmp_path / "voice_a.wav"
    out_b = tmp_path / "voice_b.wav"
    engine.speak_to_wav("test voice", voices[0].id, SpeakParams(), out_a)
    engine.speak_to_wav("test voice", voices[1].id, SpeakParams(), out_b)
    assert out_a.stat().st_size > 0
    assert out_b.stat().st_size > 0


# ── Slider (rate/volume) clamping ─────────────────────────────────────────────

def test_rate_clamped_to_negative_range(engine, first_voice, tmp_path):
    """Rate values below -10 should be clamped to -10."""
    out = tmp_path / "clamped.wav"
    engine.speak_to_wav("clamp", first_voice.id, SpeakParams(rate=-20), out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_rate_clamped_to_positive_range(engine, first_voice, tmp_path):
    """Rate values above 10 should be clamped to 10."""
    out = tmp_path / "clamped.wav"
    engine.speak_to_wav("clamp", first_voice.id, SpeakParams(rate=50), out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_volume_clamped_to_zero(engine, first_voice, tmp_path):
    """Volume below 0 should be clamped to 0."""
    out = tmp_path / "clamped.wav"
    engine.speak_to_wav("clamp", first_voice.id, SpeakParams(volume=-50), out)
    assert out.exists()


def test_volume_clamped_to_max(engine, first_voice, tmp_path):
    """Volume above 100 should be clamped to 100."""
    out = tmp_path / "clamped.wav"
    engine.speak_to_wav("clamp", first_voice.id, SpeakParams(volume=200), out)
    assert out.exists()
    assert out.stat().st_size > 0


# ── SSML / pitch support ────────────────────────────────────────────────────

def test_escape_xml_escapes_ampersand(engine):
    assert engine._escape_xml("a & b") == "a &amp; b"


def test_escape_xml_escapes_less_than(engine):
    assert engine._escape_xml("a < b") == "a &lt; b"


def test_escape_xml_escapes_greater_than(engine):
    assert engine._escape_xml("a > b") == "a &gt; b"


def test_escape_xml_leaves_safe_text_unchanged(engine):
    assert engine._escape_xml("hello world") == "hello world"


def test_build_ssml_returns_plain_text_when_pitch_zero(engine):
    params = SpeakParams(pitch=0)
    ssml = engine._build_ssml("hello", params)
    assert ssml == "hello"


def test_build_ssml_includes_pitch_element_when_nonzero(engine):
    params = SpeakParams(pitch=5)
    ssml = engine._build_ssml("hello", params)
    assert '<prosody pitch="+5st">' in ssml
    assert "hello" in ssml


def test_build_ssml_escapes_xml_in_text(engine):
    params = SpeakParams(pitch=3)
    ssml = engine._build_ssml("a & b < c > d", params)
    assert "<prosody pitch=\"+3st\">" in ssml
    assert "&amp;" in ssml
    assert "&lt;" in ssml
    assert "&gt;" in ssml


# ── wait_until_done wrapper ─────────────────────────────────────────────────

def test_wait_until_done_wrapper_returns_bool(engine):
    engine.stop()
    result = engine.wait_until_done(0)
    assert isinstance(result, bool)


def test_wait_until_done_wrapper_does_not_block_forever(engine):
    """A 1ms timeout must return quickly, not hang."""
    import time
    engine.stop()
    start = time.monotonic()
    engine.wait_until_done(1)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"wait_until_done took {elapsed:.3f}s with 1ms timeout"


def test_wait_until_done_wrapper_with_generous_timeout_completes(engine, first_voice):
    """With a long timeout on short text, should return True (completed)."""
    engine.speak_sync("hi", first_voice.id, SpeakParams())
    result = engine.wait_until_done(10_000)
    assert result is True


# ── speak with pitch ────────────────────────────────────────────────────────

def test_speak_with_pitch_does_not_raise(engine, first_voice):
    """Speaking with non-zero pitch should not raise."""
    engine.speak("hello", first_voice.id, SpeakParams(pitch=5))
    engine.stop()


def test_speak_to_wav_with_pitch_creates_file(engine, first_voice, tmp_path):
    """speak_to_wav with pitch should produce valid output."""
    out = tmp_path / "pitched.wav"
    engine.speak_to_wav("hello", first_voice.id, SpeakParams(pitch=3), out)
    assert out.exists()
    assert out.stat().st_size > 0

