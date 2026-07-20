"""Tests for ChatterboxEngine — no network, no audio hardware, no CUDA required."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.engines.base import SpeakParams
from src.engines.chatterbox_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _VALID_VOICE_IDS,
    ChatterboxEngine,
)

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = ChatterboxEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_kokoro_voices_not_in_roster():
    for vid in ("af_heart", "bf_emma", "am_adam"):
        assert vid not in _VALID_VOICE_IDS


# ── Voice validation guard ────────────────────────────────────────────────────

def _make_mock_model(audio: np.ndarray):
    """Return a mock ChatterboxTTS whose generate() returns a tensor-like object."""
    import torch
    mock = MagicMock()
    mock.generate.return_value = torch.from_numpy(audio).unsqueeze(0)  # shape (1, N)
    return mock


def test_invalid_voice_falls_back_to_default():
    audio = np.zeros(100, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = ChatterboxEngine()
    ChatterboxEngine._model = mock_model

    with patch("src.engines.chatterbox_engine.play_audio"):
        engine.speak("hello", "af_heart", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    # generate() must have been called (invalid voice → default used)
    mock_model.generate.assert_called_once_with("hello")


def test_valid_voice_passes_through():
    audio = np.zeros(100, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = ChatterboxEngine()
    ChatterboxEngine._model = mock_model

    with patch("src.engines.chatterbox_engine.play_audio"):
        engine.speak("hello", "default", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    mock_model.generate.assert_called_once()


# ── speak ─────────────────────────────────────────────────────────────────────

def test_speak_calls_play_audio():
    audio = np.ones(2400, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = ChatterboxEngine()
    ChatterboxEngine._model = mock_model

    played = []
    with patch("src.engines.chatterbox_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("test", "default", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert abs(arr[0] - 0.5) < 0.01  # volume 50 → scale 0.5


def test_speak_empty_text_does_nothing():
    engine = ChatterboxEngine()
    ChatterboxEngine._model = MagicMock()
    with patch("src.engines.chatterbox_engine.play_audio") as mock_play:
        engine.speak("", "default", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


def test_speak_whitespace_only_does_nothing():
    audio = np.zeros(100, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = ChatterboxEngine()
    ChatterboxEngine._model = mock_model
    with patch("src.engines.chatterbox_engine.play_audio") as mock_play:
        engine.speak("   ", "default", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = ChatterboxEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = ChatterboxEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_done():
    engine = ChatterboxEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = ChatterboxEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False


def test_stop_mid_generation_skips_playback():
    """If stop() is called while generate() is blocking, play_audio must not be called."""
    import threading
    generating = threading.Event()
    resume = threading.Event()

    def slow_generate(text):
        import torch
        generating.set()
        resume.wait(timeout=3.0)
        return torch.zeros(1, 100)

    mock_model = MagicMock()
    mock_model.generate.side_effect = slow_generate
    engine = ChatterboxEngine()
    ChatterboxEngine._model = mock_model

    played = []
    with patch("src.engines.chatterbox_engine.play_audio",
               side_effect=lambda a, r: played.append(a)):
        engine.speak("long text", "default", SpeakParams())
        generating.wait(timeout=3.0)
        engine.stop()
        resume.set()
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 0, "play_audio must not be called after stop()"
