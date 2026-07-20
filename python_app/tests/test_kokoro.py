"""Tests for KokoroEngine — no network, no audio hardware required.

All tests mock the KPipeline and sounddevice so they run in CI without
model weights on disk and without a sound card.
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


# ── Voice validation guard ────────────────────────────────────────────────────

def _make_mock_pipeline(audio: np.ndarray):
    """Return a mock KPipeline that yields one audio chunk."""
    mock_pipe = MagicMock()
    mock_pipe.return_value = iter([("gs", "ps", audio)])
    return mock_pipe


def _used_voice(mock_pipe) -> str:
    """Extract the voice kwarg from the last call to a mock pipeline."""
    return mock_pipe.call_args.kwargs["voice"]


def test_invalid_voice_falls_back_to_default():
    """Passing a Piper voice ID must use _DEFAULT_VOICE instead — no network call."""
    audio = np.zeros(100, dtype=np.float32)
    mock_pipe = _make_mock_pipeline(audio)

    engine = KokoroEngine()

    with patch.object(engine, "_get_pipeline", return_value=mock_pipe), \
         patch("src.engines.kokoro_engine.play_audio"):
        engine.speak("hello", "en_US-amy-medium", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert _used_voice(mock_pipe) == _DEFAULT_VOICE


def test_valid_voice_passes_through():
    """A valid Kokoro voice ID must reach the pipeline unchanged."""
    audio = np.zeros(100, dtype=np.float32)
    mock_pipe = _make_mock_pipeline(audio)

    engine = KokoroEngine()

    with patch.object(engine, "_get_pipeline", return_value=mock_pipe), \
         patch("src.engines.kokoro_engine.play_audio"):
        engine.speak("hello", "bf_emma", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert _used_voice(mock_pipe) == "bf_emma"


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


# ── speak with mocked pipeline ────────────────────────────────────────────────

def test_speak_calls_play_audio():
    audio = np.ones(2400, dtype=np.float32)
    mock_pipe = _make_mock_pipeline(audio)

    engine = KokoroEngine()
    played = []

    with patch.object(engine, "_get_pipeline", return_value=mock_pipe), \
         patch("src.engines.kokoro_engine.play_audio", side_effect=lambda a, r: played.append((a, r))):
        engine.speak("test", "af_heart", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == 24_000
    # Volume 50 → scale 0.5
    assert abs(arr[0] - 0.5) < 0.01


def test_speak_empty_text_does_nothing():
    engine = KokoroEngine()
    with patch.object(engine, "_get_pipeline") as mock_get:
        engine.speak("", "af_heart", SpeakParams())
        mock_get.assert_not_called()


def test_stop_mid_generation_aborts():
    """If stop() is called while the generator is running, play_audio must not be called."""
    first_chunk_reached = threading.Event()
    stop_was_set = threading.Event()

    def blocking_pipe(**kwargs):
        # Yield first chunk and signal the test thread, then block until stop is set
        yield "gs", "ps", np.zeros(100, dtype=np.float32)
        first_chunk_reached.set()
        stop_was_set.wait(timeout=3.0)
        # Yield more chunks — these must be discarded because stop was requested
        for _ in range(5):
            yield "gs", "ps", np.zeros(100, dtype=np.float32)

    mock_pipe = MagicMock(side_effect=blocking_pipe)
    engine = KokoroEngine()

    played = []
    with patch.object(engine, "_get_pipeline", return_value=mock_pipe), \
         patch("src.engines.kokoro_engine.play_audio", side_effect=lambda a, r: played.append(a)):
        engine.speak("long text", "af_heart", SpeakParams())
        first_chunk_reached.wait(timeout=3.0)  # wait until generator is running
        engine.stop()
        stop_was_set.set()
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 0, "play_audio must not be called after stop()"
