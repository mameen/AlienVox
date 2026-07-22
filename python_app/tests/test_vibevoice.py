"""Tests for VibeVoiceEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy: real-synthesis tests are gated by @requires_vibevoice_weights
(skip, not fail, when the ~2GB weights aren't present locally) rather than
mocking generate() — see docs/issues/todo_006.md for the real local
benchmark this engine's implementation is based on (measured RTF ~2.5x on
CPU, i.e. not real-time despite the "Realtime" name).
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np

from src.engines.base import SpeakParams
from src.engines.vibevoice_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _VALID_VOICE_IDS,
    _VOICE_TO_PT,
    VibeVoiceEngine,
    apply_volume,
)

from .conftest import requires_gpu, requires_weights

requires_vibevoice_weights = requires_weights("ml/vibevoice_realtime")

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_known_voices_in_roster():
    for vid in ("carter", "davis", "frank", "mike", "emma", "grace"):
        assert vid in _VALID_VOICE_IDS


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = VibeVoiceEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_other_engine_voices_not_in_roster():
    for vid in ("af_heart", "s1", "default", "male_1"):
        assert vid not in _VALID_VOICE_IDS


def test_every_voice_maps_to_a_distinct_pt_file():
    """Each preset voice must resolve to its own .pt filename — a collision
    here would mean two voices silently sound identical."""
    filenames = set(_VOICE_TO_PT.values())
    assert len(filenames) == len(_VOICE_TO_PT)
    assert all(f.endswith(".pt") for f in filenames)


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_vibevoice_weights
def test_real_synthesis_produces_audio_with_correct_rate():
    engine = VibeVoiceEngine()
    result = engine.synthesize("Hello, this is a real VibeVoice test.", "carter", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100
    assert np.abs(audio).max() <= 1.0


@requires_vibevoice_weights
def test_real_synthesis_female_voice_produces_audio():
    """Explicit coverage for a female preset (emma), not just the default (carter)."""
    engine = VibeVoiceEngine()
    result = engine.synthesize("This is Emma speaking a real test phrase.", "emma", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100


# ── apply_volume: pure logic, no model/mocking needed ─────────────────────────
#
# Deliberately NOT tested by comparing two independent real generate() calls
# at different volumes (the pattern test_piper.py/test_f5tts.py use) —
# confirmed via real testing that VibeVoice's autoregressive GPU generation
# isn't reproducible enough call-to-call for that comparison to be sound (two
# real runs of the identical input produced different generated-token counts
# and, once, a HIGHER peak at the "lower" volume — proving the underlying
# content differed, not just its scale). apply_volume() is the actual thing
# that needs correctness, and it's a pure function — test it directly.

def test_apply_volume_full_is_unchanged():
    audio = np.array([0.5, -0.8, 0.2], dtype=np.float32)
    result = apply_volume(audio, 100)
    np.testing.assert_allclose(result, audio)


def test_apply_volume_half_scales_by_half():
    audio = np.array([0.5, -0.8, 0.2], dtype=np.float32)
    result = apply_volume(audio, 50)
    np.testing.assert_allclose(result, audio * 0.5)


def test_apply_volume_zero_silences():
    audio = np.array([0.5, -0.8, 0.2], dtype=np.float32)
    result = apply_volume(audio, 0)
    np.testing.assert_allclose(result, np.zeros_like(audio))


def test_apply_volume_clamps_out_of_range():
    audio = np.array([1.0], dtype=np.float32)
    np.testing.assert_allclose(apply_volume(audio, 200), audio)      # clamped to 100
    np.testing.assert_allclose(apply_volume(audio, -50), audio * 0)  # clamped to 0


@requires_vibevoice_weights
def test_real_synthesis_produces_nonzero_audio_at_full_volume():
    """One real generate() call, proving the real engine path actually
    reaches apply_volume() and doesn't silently zero out output — the
    correctness of the scaling itself is covered by the pure tests above."""
    engine = VibeVoiceEngine()
    result = engine.synthesize("volume smoke test phrase", "carter", SpeakParams(volume=100))
    assert result is not None
    audio, _ = result
    assert np.abs(audio).max() > 0


@requires_vibevoice_weights
def test_real_synthesis_invalid_voice_falls_back_to_default():
    engine = VibeVoiceEngine()
    result = engine.synthesize("fallback test", "not_a_real_voice", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100


@requires_vibevoice_weights
def test_real_speak_calls_play_audio():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer comes from real VibeVoice synthesis."""
    engine = VibeVoiceEngine()
    played = []
    with patch("src.engines.vibevoice_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("real playback test", "carter", SpeakParams())
        engine.wait_until_done(timeout_ms=60_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert len(arr) > 0
    assert np.abs(arr).max() > 0


def test_speak_empty_text_does_nothing():
    """No mocking of the model needed — empty text must short-circuit
    before ever touching _get_model_and_processor(), real or otherwise."""
    engine = VibeVoiceEngine()
    with patch("src.engines.vibevoice_engine.play_audio") as mock_play:
        engine.speak("", "carter", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = VibeVoiceEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = VibeVoiceEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_set():
    engine = VibeVoiceEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = VibeVoiceEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False


# ── Device selection (hardware-conditional) ───────────────────────────────────

@requires_gpu
@requires_vibevoice_weights
def test_model_loads_on_cuda_when_gpu_available():
    """On a real CUDA machine, the model singleton must actually be moved
    to the GPU device — checked via the real loaded model's parameters,
    not a mock, since select_device()/device placement is exactly the
    thing worth verifying for real."""
    VibeVoiceEngine._model = None
    VibeVoiceEngine._processor = None
    engine = VibeVoiceEngine()
    model, _ = engine._get_model_and_processor()
    assert next(model.parameters()).is_cuda
    VibeVoiceEngine._model = None  # reset singleton for other tests
    VibeVoiceEngine._processor = None
