"""Tests for ChatterboxEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy, real-synthesis tests run against the actual downloaded
Chatterbox model (gated by @requires_weights — real generate() calls take
~10-25s each, including one-time model load, so these are consolidated
into as few real calls as practical). Voice-fallback and threading/abort
tests remain mocked with justification: real generation timing can't be
paused at a reproducible point mid-stream, and repeatedly reloading a
multi-GB model just to test our own threading logic isn't a productive
trade — those tests exercise our orchestration code given a
generate()-shaped callable, not Chatterbox's actual behavior.
"""
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

from .conftest import requires_gpu, requires_weights

requires_chatterbox_weights = requires_weights("ml/chatterbox")

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


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_chatterbox_weights
def test_real_synthesis_produces_audio_for_valid_and_invalid_voice():
    """Real model, real generate() call. Chatterbox only has one voice
    ("default"), so this also proves an unrecognized voice ID falls back to
    it rather than erroring — both paths converge on the same real call."""
    engine = ChatterboxEngine()

    result_valid = engine.synthesize("Hello, this is a real Chatterbox test.", "default", SpeakParams())
    assert result_valid is not None
    audio, sr = result_valid
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100
    assert np.abs(audio).max() <= 1.0

    result_invalid_voice = engine.synthesize("Hello again.", "af_heart", SpeakParams())
    assert result_invalid_voice is not None  # falls back to "default", still produces audio


@requires_chatterbox_weights
def test_real_speak_calls_play_audio_with_volume_scaling():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer comes from real Chatterbox synthesis, and volume scaling
    is verified against a real waveform's actual peak amplitude."""
    engine = ChatterboxEngine()

    played = []
    with patch("src.engines.chatterbox_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("consistent volume test phrase", "default", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=60_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert len(arr) > 0

    full = engine.synthesize("consistent volume test phrase", "default", SpeakParams(volume=100))
    assert full is not None
    full_audio, _ = full
    full_peak = np.abs(full_audio).max()
    half_peak = np.abs(arr).max()
    assert full_peak > 0
    assert abs(half_peak - full_peak * 0.5) < full_peak * 0.05


def test_speak_empty_text_does_nothing():
    """No mocking needed — empty text must short-circuit before ever
    touching _get_model(), real or otherwise."""
    engine = ChatterboxEngine()
    with patch("src.engines.chatterbox_engine.play_audio") as mock_play:
        engine.speak("", "default", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


def test_speak_whitespace_only_does_nothing():
    engine = ChatterboxEngine()
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


# ── Device selection (hardware-conditional) ───────────────────────────────────

@requires_gpu
def test_get_model_selects_cuda_device_when_gpu_available(monkeypatch):
    """On a real CUDA machine, _get_model() must request device='cuda', not 'cpu'."""
    ChatterboxEngine._model = None
    captured = {}

    def fake_from_pretrained(device):
        captured["device"] = device
        return MagicMock()

    mock_module = MagicMock()
    mock_module.ChatterboxTTS.from_pretrained.side_effect = fake_from_pretrained
    with patch.dict("sys.modules", {"chatterbox.tts": mock_module}):
        engine = ChatterboxEngine()
        engine._get_model()

    assert captured["device"] == "cuda"
    ChatterboxEngine._model = None  # reset singleton for other tests
