"""Tests for KokoroEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy, tests that exercise KPipeline/synthesis logic run against the
REAL model (gated by @requires_weights, skipped if .models/ml/kokoro isn't
populated — run `python run.py download` to populate it). Only two
exceptions remain mocked, both justified below:
  - play_audio is intercepted so test runs don't emit real audio to your
    speakers or require an audio device — the audio *array* produced by
    real synthesis is still captured and asserted on for real.
  - test_stop_mid_generation_aborts needs to interrupt generation at a
    precise, reproducible point mid-stream; real inference timing isn't
    controllable enough to make that deterministic, so a fake generator
    stands in there specifically to test our own threading/abort logic
    (not Kokoro's behavior).
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.kokoro_engine import (
    KokoroEngine,
    _DEFAULT_VOICE,
    _VALID_VOICE_IDS,
    _rate_to_speed,
)

from .conftest import requires_weights

requires_kokoro_weights = requires_weights("ml/kokoro")


# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_are_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_known_voices_in_valid_set():
    assert "af_heart" in _VALID_VOICE_IDS
    assert "bm_george" in _VALID_VOICE_IDS


def test_piper_voice_not_in_valid_set():
    """Cross-contamination guard: Piper voice IDs must not be in Kokoro's roster."""
    piper_voices = [
        "en_US-lessac-medium",
        "en_US-amy-medium",
        "en_GB-alan-medium",
        "en_US-ryan-high",
    ]
    for vid in piper_voices:
        assert vid not in _VALID_VOICE_IDS, f"{vid!r} must not be a valid Kokoro voice"


def test_list_voices_returns_all():
    engine = KokoroEngine()
    voices = engine.list_voices()
    ids = {v.id for v in voices}
    assert ids == _VALID_VOICE_IDS


# ── Rate → speed mapping ──────────────────────────────────────────────────────

@pytest.mark.parametrize("rate,expected", [
    (0,   1.0),
    (10,  2.0),
    (-10, 0.5),
    (5,   1.5),
    (-5,  0.75),
])
def test_rate_to_speed(rate, expected):
    assert abs(_rate_to_speed(rate) - expected) < 0.01


def test_rate_clamped_above():
    assert _rate_to_speed(99) == _rate_to_speed(10)


def test_rate_clamped_below():
    assert _rate_to_speed(-99) == _rate_to_speed(-10)


# ── stop() ────────────────────────────────────────────────────────────────────

def test_stop_sets_done_event():
    engine = KokoroEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = KokoroEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


# ── wait_until_done ───────────────────────────────────────────────────────────

def test_wait_until_done_returns_true_when_done():
    engine = KokoroEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = KokoroEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False


def test_speak_empty_text_does_nothing():
    engine = KokoroEngine()
    with patch.object(engine, "_get_pipeline") as mock_get:
        engine.speak("", "af_heart", SpeakParams())
        mock_get.assert_not_called()


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_kokoro_weights
def test_real_synthesis_invalid_voice_falls_back_to_default():
    """Passing a Piper voice ID must fall back to _DEFAULT_VOICE and still
    produce real audio — proves the fallback path, not just that it doesn't
    crash."""
    engine = KokoroEngine()
    result = engine.synthesize("hello", "en_US-amy-medium", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == 24_000
    assert len(audio) > 0
    assert audio.dtype == np.float32


@requires_kokoro_weights
def test_real_synthesis_valid_voice_produces_audio():
    engine = KokoroEngine()
    result = engine.synthesize("hello world, this is a real synthesis test.", "bf_emma", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == 24_000
    assert len(audio) > 100  # more than a trivial/empty buffer
    assert np.abs(audio).max() <= 1.0  # valid float32 PCM range


@requires_kokoro_weights
def test_real_synthesis_volume_scaling():
    """Real synthesized audio at volume=50 should have roughly half the peak
    amplitude of the same text/voice at volume=100."""
    engine = KokoroEngine()
    full = engine.synthesize("consistent test phrase for volume", "af_heart", SpeakParams(volume=100))
    half = engine.synthesize("consistent test phrase for volume", "af_heart", SpeakParams(volume=50))
    assert full is not None and half is not None
    full_audio, _ = full
    half_audio, _ = half
    full_peak = np.abs(full_audio).max()
    half_peak = np.abs(half_audio).max()
    assert full_peak > 0
    assert abs(half_peak - full_peak * 0.5) < full_peak * 0.05  # within 5% tolerance


@requires_kokoro_weights
def test_real_speak_calls_play_audio_with_real_buffer():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer it receives comes from real Kokoro synthesis."""
    engine = KokoroEngine()
    played = []
    with patch("src.engines.kokoro_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("real playback test", "af_heart", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=30_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == 24_000
    assert len(arr) > 0
    assert np.abs(arr).max() > 0  # not silence


# ── Threading / abort semantics (fake generator — see module docstring) ───────

def test_stop_mid_generation_aborts():
    """If stop() is called while the generator is running, play_audio must
    not be called. Uses a fake generator (not Kokoro's real pipeline) to
    deterministically control *when* mid-stream interruption happens — real
    inference timing can't be paused at a reproducible point. This tests
    our own threading/abort logic, independent of what Kokoro itself does."""
    first_chunk_reached = threading.Event()
    stop_was_set = threading.Event()

    def blocking_pipe(**kwargs):
        yield "gs", "ps", np.zeros(100, dtype=np.float32)
        first_chunk_reached.set()
        stop_was_set.wait(timeout=3.0)
        for _ in range(5):
            yield "gs", "ps", np.zeros(100, dtype=np.float32)

    mock_pipe = MagicMock(side_effect=blocking_pipe)
    engine = KokoroEngine()

    played = []
    with patch.object(engine, "_get_pipeline", return_value=mock_pipe), \
         patch("src.engines.kokoro_engine.play_audio", side_effect=lambda a, r: played.append(a)):
        engine.speak("long text", "af_heart", SpeakParams())
        first_chunk_reached.wait(timeout=3.0)
        engine.stop()
        stop_was_set.set()
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 0, "play_audio must not be called after stop()"
