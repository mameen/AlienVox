"""Tests for OuteTTSEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy: voice-to-speaker-name resolution was extracted into a pure
resolve_speaker_name() function (outetts_engine.py) so it's testable with
zero mocking. Real generate() calls take ~15-20s including one-time model
load, so real-synthesis tests below are consolidated into the minimum
number of real calls needed to cover audio validity, sample rate, int16
normalization, and volume scaling — all gated by @requires_weights.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.engines.base import SpeakParams
from src.engines.outetts_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _VALID_VOICE_IDS,
    _VOICE_TO_SPEAKER,
    OuteTTSEngine,
    apply_volume,
    resolve_speaker_name,
)

from .conftest import requires_gpu, requires_weights

requires_outetts_weights = requires_weights("ml/outetts")

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_known_voices_in_roster():
    for vid in ("male_1", "male_2", "male_3", "female_1"):
        assert vid in _VALID_VOICE_IDS


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = OuteTTSEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_kokoro_voices_not_in_roster():
    for vid in ("af_heart", "s1", "default", "en_female_calm"):
        assert vid not in _VALID_VOICE_IDS


# ── resolve_speaker_name: pure logic, no model/mocking needed ────────────────

def test_invalid_voice_falls_back_to_default_speaker():
    assert resolve_speaker_name("bad_voice") == _VOICE_TO_SPEAKER[_DEFAULT_VOICE]


def test_valid_voice_resolves_to_real_speaker_name():
    """Our short voice IDs must be translated to outetts's real speaker names
    (language-prefixed, e.g. en_female_1) — see _VOICE_TO_SPEAKER."""
    assert resolve_speaker_name("female_1") == "en_female_1"


def test_all_roster_voices_resolve_to_distinct_speakers():
    resolved = {resolve_speaker_name(v) for v in _VALID_VOICE_IDS}
    assert len(resolved) == len(_VALID_VOICE_IDS)


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_outetts_weights
def test_real_synthesis_produces_audio_with_correct_rate():
    engine = OuteTTSEngine()
    result = engine.synthesize("Hello, this is a real OuteTTS test.", "male_1", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100
    assert np.abs(audio).max() <= 1.0  # int16-range normalization applied


# ── apply_volume: pure logic, no model/mocking needed ─────────────────────────
#
# Deliberately NOT tested by comparing two independent real generate() calls
# at different volumes — confirmed (same root cause as vibevoice_engine.py's
# apply_volume) that real generation isn't reproducible enough call-to-call
# for that comparison to be sound. apply_volume() is the actual thing that
# needs correctness, and it's a pure function — test it directly.

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


@requires_outetts_weights
def test_real_synthesis_produces_nonzero_audio_at_full_volume():
    """One real generate() call, proving the real engine path actually
    reaches apply_volume() and doesn't silently zero out output — the
    correctness of the scaling itself is covered by the pure tests above."""
    engine = OuteTTSEngine()
    result = engine.synthesize("volume smoke test phrase", "male_1", SpeakParams(volume=100))
    assert result is not None
    audio, _ = result
    assert np.abs(audio).max() > 0


@requires_outetts_weights
def test_real_speak_calls_play_audio():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer comes from real OuteTTS synthesis."""
    engine = OuteTTSEngine()
    played = []
    with patch("src.engines.outetts_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("real playback test", "female_1", SpeakParams())
        engine.wait_until_done(timeout_ms=30_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert len(arr) > 0
    assert np.abs(arr).max() > 0


def test_speak_empty_text_does_nothing():
    """No mocking needed — empty text must short-circuit before ever
    touching _get_interface(), real or otherwise."""
    engine = OuteTTSEngine()
    with patch("src.engines.outetts_engine.play_audio") as mock_play:
        engine.speak("", "male_1", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


def test_int16_audio_normalised_to_float():
    """int16-range audio (max > 1.0) must be normalised before playback.

    Stubs generate()'s return value specifically to exercise this
    defensive branch — whether real OuteTTS ever actually returns
    int16-range floats isn't guaranteed/reproducible, but our code must
    handle it correctly if it does."""
    import torch
    audio_int16 = np.full(100, 16384, dtype=np.float32)  # simulates int16 range
    output = MagicMock()
    output.audio = torch.from_numpy(audio_int16).unsqueeze(0)
    mock_iface = MagicMock()
    mock_iface.generate.return_value = output
    mock_iface.load_default_speaker.return_value = MagicMock()

    engine = OuteTTSEngine()
    OuteTTSEngine._interface = mock_iface

    played = []
    with patch("src.engines.outetts_engine.play_audio",
               side_effect=lambda a, r: played.append(a)):
        engine.speak("test", "male_1", SpeakParams(volume=100))
        engine.wait_until_done(timeout_ms=15_000)

    assert len(played) == 1
    assert played[0].max() <= 1.0


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = OuteTTSEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = OuteTTSEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_set():
    engine = OuteTTSEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = OuteTTSEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False


# ── Device selection (hardware-conditional) ───────────────────────────────────

@requires_gpu
def test_get_interface_selects_cuda_device_when_gpu_available():
    """On a real CUDA machine, _get_interface() must request device='cuda'."""
    OuteTTSEngine._interface = None
    captured = {}

    mock_outetts = MagicMock()

    def fake_config(model_path, tokenizer_path, device):
        captured["device"] = device
        return MagicMock()

    mock_outetts.HFModelConfig_v2.side_effect = fake_config
    mock_outetts.InterfaceHF.side_effect = lambda model_version, cfg: MagicMock()

    with patch.dict("sys.modules", {"outetts": mock_outetts}):
        engine = OuteTTSEngine()
        engine._get_interface()

    assert captured["device"] == "cuda"
    OuteTTSEngine._interface = None  # reset singleton for other tests
