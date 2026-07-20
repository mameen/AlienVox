"""Tests for PiperEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy, real-synthesis tests below run against the actual downloaded
Piper voice model (gated by @requires_weights). A handful of tests still
use a mocked PiperVoice, each justified individually:
  - Silence-gap arithmetic (test_synthesize_concatenates_chunks_and_applies_volume,
    test_synthesize_no_silence_gap_when_sentence_silence_zero) needs exact
    control over chunk sample counts to assert precise concatenation math —
    real inference output length isn't controllable enough for that.
  - test_synthesize_returns_none_on_exception tests our own error-handling
    path, which requires forcing an exception deterministically.
  - play_audio is intercepted in the real-synthesis playback test so it
    doesn't require an audio device / emit real sound in CI.

Covers two real bugs found and fixed:
  1. _synthesize() was a stub that always returned b"" — Piper never
     actually produced audio despite weights being present.
  2. Piper-specific extra controls (noise_scale, noise_w, sentence_silence)
     declared in stacks.yaml were read via params.__dict__.get(...), but
     nothing ever set those attributes on SpeakParams — piper_config_from_params()
     now reads from the typed SpeakParams.extra dict instead.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.piper_win import (
    PiperEngine,
    piper_config_from_params,
    rate_to_length_scale,
)

from .conftest import requires_weights

requires_piper_weights = requires_weights("ml/piper")
_REAL_VOICE = "en_US-lessac-medium"  # confirmed present under .models/ml/piper


# ── piper_config_from_params: defaults ──────────────────────────────────────

def test_config_uses_defaults_when_extra_empty():
    cfg = piper_config_from_params(SpeakParams())
    assert cfg == {"noise_scale": 0.667, "noise_w": 0.8, "sentence_silence": 0.2}


# ── piper_config_from_params: overrides flow through ────────────────────────

def test_config_honors_noise_scale_override():
    cfg = piper_config_from_params(SpeakParams(extra={"noise_scale": 0.9}))
    assert cfg["noise_scale"] == 0.9
    assert cfg["noise_w"] == 0.8
    assert cfg["sentence_silence"] == 0.2


def test_config_honors_noise_w_override():
    cfg = piper_config_from_params(SpeakParams(extra={"noise_w": 0.3}))
    assert cfg["noise_w"] == 0.3


def test_config_honors_sentence_silence_override():
    cfg = piper_config_from_params(SpeakParams(extra={"sentence_silence": 1.5}))
    assert cfg["sentence_silence"] == 1.5


def test_config_honors_all_overrides_together():
    cfg = piper_config_from_params(
        SpeakParams(extra={"noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3})
    )
    assert cfg == {"noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3}


def test_config_ignores_unrelated_extra_keys():
    cfg = piper_config_from_params(SpeakParams(extra={"unrelated_key": 42}))
    assert cfg == {"noise_scale": 0.667, "noise_w": 0.8, "sentence_silence": 0.2}


# ── rate_to_length_scale ──────────────────────────────────────────────────────

def test_rate_zero_is_length_scale_one():
    assert rate_to_length_scale(0) == pytest.approx(1.0)


def test_rate_positive_shortens_length_scale():
    """Higher rate = faster speech = smaller length_scale."""
    assert rate_to_length_scale(10) < 1.0


def test_rate_negative_lengthens_length_scale():
    """Lower rate = slower speech = larger length_scale."""
    assert rate_to_length_scale(-10) > 1.0


def test_rate_clamped_to_bounds():
    assert rate_to_length_scale(999) == rate_to_length_scale(10)
    assert rate_to_length_scale(-999) == rate_to_length_scale(-10)
    assert 0.5 <= rate_to_length_scale(999) <= 2.0


# ── _synthesize_array with a mocked PiperVoice model ─────────────────────────

def _make_chunk(audio: np.ndarray, sample_rate: int = 22_050):
    chunk = MagicMock()
    chunk.audio_float_array = audio
    chunk.sample_rate = sample_rate
    return chunk


def test_synthesize_returns_none_for_empty_text():
    engine = PiperEngine()
    assert engine._synthesize_array("", "en_US-lessac-medium", SpeakParams()) is None


def test_synthesize_returns_none_when_voice_not_found():
    """Real path — no mocking: a voice ID with no matching .onnx file under
    .models/ml/piper must fail to resolve, regardless of whether weights for
    other voices are present."""
    engine = PiperEngine()
    result = engine._synthesize_array("hello", "nonexistent-voice-xyz", SpeakParams())
    assert result is None


def test_synthesize_concatenates_chunks_and_applies_volume():
    mock_voice = MagicMock()
    chunk1 = _make_chunk(np.ones(100, dtype=np.float32))
    chunk2 = _make_chunk(np.ones(50, dtype=np.float32))
    mock_voice.synthesize.return_value = iter([chunk1, chunk2])

    engine = PiperEngine()
    with patch.object(engine, "_get_voice_model", return_value=mock_voice):
        result = engine._synthesize_array(
            "hello world", "en_US-lessac-medium", SpeakParams(volume=50)
        )

    assert result is not None
    audio, sr = result
    assert sr == 22_050
    # Two chunks + one silence gap (sentence_silence default 0.2s @ 22050Hz = 4410 samples)
    assert len(audio) == 100 + 4410 + 50
    assert abs(audio[0] - 0.5) < 1e-4  # volume=50 -> scale 0.5


def test_synthesize_no_silence_gap_when_sentence_silence_zero():
    mock_voice = MagicMock()
    chunk1 = _make_chunk(np.ones(10, dtype=np.float32))
    chunk2 = _make_chunk(np.ones(10, dtype=np.float32))
    mock_voice.synthesize.return_value = iter([chunk1, chunk2])

    engine = PiperEngine()
    with patch.object(engine, "_get_voice_model", return_value=mock_voice):
        result = engine._synthesize_array(
            "hi", "en_US-lessac-medium",
            SpeakParams(extra={"sentence_silence": 0.0}),
        )

    audio, _ = result
    assert len(audio) == 20  # no silence inserted between the two chunks


def test_synthesize_returns_none_on_exception():
    mock_voice = MagicMock()
    mock_voice.synthesize.side_effect = RuntimeError("onnx failure")

    engine = PiperEngine()
    with patch.object(engine, "_get_voice_model", return_value=mock_voice):
        result = engine._synthesize_array("hello", "en_US-lessac-medium", SpeakParams())

    assert result is None


def test_synthesize_stops_early_when_stop_requested():
    mock_voice = MagicMock()
    chunk1 = _make_chunk(np.ones(10, dtype=np.float32))
    mock_voice.synthesize.return_value = iter([chunk1])

    engine = PiperEngine()
    engine._stop_requested.set()
    with patch.object(engine, "_get_voice_model", return_value=mock_voice):
        result = engine._synthesize_array("hello", "en_US-lessac-medium", SpeakParams())

    assert result is None


def test_speak_empty_text_does_nothing():
    engine = PiperEngine()
    with patch.object(engine, "_get_voice_model") as mock_get:
        engine.speak("", "en_US-lessac-medium", SpeakParams())
        mock_get.assert_not_called()


def test_stop_sets_done_event():
    engine = PiperEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_piper_weights
def test_real_synthesis_produces_audio():
    engine = PiperEngine()
    result = engine.synthesize(
        "Hello, this is a real Piper synthesis test.", _REAL_VOICE, SpeakParams()
    )
    assert result is not None
    audio, sr = result
    assert sr == 22_050
    assert len(audio) > 100
    assert np.abs(audio).max() <= 1.0


@requires_piper_weights
def test_real_synthesis_volume_scaling():
    engine = PiperEngine()
    full = engine.synthesize("consistent phrase for volume", _REAL_VOICE, SpeakParams(volume=100))
    half = engine.synthesize("consistent phrase for volume", _REAL_VOICE, SpeakParams(volume=50))
    assert full is not None and half is not None
    full_audio, _ = full
    half_audio, _ = half
    full_peak = np.abs(full_audio).max()
    half_peak = np.abs(half_audio).max()
    assert full_peak > 0
    assert abs(half_peak - full_peak * 0.5) < full_peak * 0.05


@requires_piper_weights
def test_real_synthesis_honors_noise_scale_override():
    """A real noise_scale override must actually reach piper's synthesis
    config and change output — not just be accepted and ignored."""
    engine = PiperEngine()
    default_result = engine.synthesize("noise scale test phrase", _REAL_VOICE, SpeakParams())
    overridden_result = engine.synthesize(
        "noise scale test phrase", _REAL_VOICE,
        SpeakParams(extra={"noise_scale": 0.0, "noise_w": 0.0}),
    )
    assert default_result is not None and overridden_result is not None
    default_audio, _ = default_result
    overridden_audio, _ = overridden_result
    # Different noise settings should produce a measurably different waveform
    # (same length is fine — same phrase/voice — but values should differ).
    assert not np.allclose(default_audio[:1000], overridden_audio[:1000])


@requires_piper_weights
def test_real_speak_calls_play_audio_with_real_buffer():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer it receives comes from real Piper synthesis."""
    engine = PiperEngine()
    played = []
    with patch("src.engines.piper_win.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("real playback test", _REAL_VOICE, SpeakParams())
        engine.wait_until_done(timeout_ms=30_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == 22_050
    assert len(arr) > 0
    assert np.abs(arr).max() > 0
