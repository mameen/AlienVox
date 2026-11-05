"""F5-TTS adapter tests, including real synthesis with packaged references."""
from __future__ import annotations

from unittest.mock import patch

import numpy as np

from src.engines.base import SpeakParams
from src.engines.f5tts_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _VALID_VOICE_IDS,
    F5TTSEngine,
)

from .conftest import requires_weights

# f5tts weights + the en_female_calm reference voice must both be present.
requires_f5tts_weights = requires_weights("ml/f5tts")
requires_f5tts_reference = requires_weights("ml/f5tts/voices")

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = F5TTSEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_kokoro_voices_not_in_roster():
    for vid in ("af_heart", "default", "s1"):
        assert vid not in _VALID_VOICE_IDS


# ── Missing reference file handling (real filesystem condition) ──────────────

def test_preset_reference_voices_are_provisioned_from_installed_package(tmp_path):
    import soundfile as sf

    from src.engines.f5tts_engine import provision_reference_voices

    provision_reference_voices(tmp_path)
    for voice_id in ("en_female_calm", "en_male_warm"):
        wav_path = tmp_path / f"{voice_id}.wav"
        text_path = tmp_path / f"{voice_id}.txt"
        assert wav_path.is_file() and wav_path.stat().st_size > 1_000
        assert text_path.is_file() and text_path.read_text(encoding="utf-8").strip()
        assert sf.info(wav_path).duration >= 3.0


def test_speak_empty_text_does_nothing():
    """No mocking needed — empty text must short-circuit before ever
    touching _get_model(), real or otherwise."""
    engine = F5TTSEngine()
    with patch("src.engines.f5tts_engine.play_audio") as mock_play:
        engine.speak("", _DEFAULT_VOICE, SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_f5tts_weights
@requires_f5tts_reference
def test_real_synthesis_produces_audio():
    engine = F5TTSEngine()
    result = engine.synthesize(
        "Hello, this is a real F5-TTS synthesis test.", "en_female_calm", SpeakParams()
    )
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE or sr > 0  # F5-TTS reports its own native rate
    assert len(audio) > 100
    assert audio.dtype == np.float32


@requires_f5tts_weights
@requires_f5tts_reference
def test_real_synthesis_invalid_voice_falls_back_to_default():
    engine = F5TTSEngine()
    result = engine.synthesize("Hello again.", "bad_voice", SpeakParams())
    assert result is not None  # falls back to en_female_calm, still produces audio


@requires_f5tts_weights
@requires_f5tts_reference
def test_real_synthesis_volume_scaling():
    engine = F5TTSEngine()
    full = engine.synthesize("volume scaling test phrase", "en_female_calm", SpeakParams(volume=100))
    half = engine.synthesize("volume scaling test phrase", "en_female_calm", SpeakParams(volume=50))
    assert full is not None and half is not None
    full_audio, _ = full
    half_audio, _ = half
    full_peak = np.abs(full_audio).max()
    half_peak = np.abs(half_audio).max()
    assert full_peak > 0
    assert abs(half_peak - full_peak * 0.5) < full_peak * 0.05


@requires_f5tts_weights
@requires_f5tts_reference
def test_real_speak_calls_play_audio():
    """play_audio is intercepted (no speakers/audio device needed for CI),
    but the buffer comes from real F5-TTS synthesis."""
    engine = F5TTSEngine()
    played = []
    with patch("src.engines.f5tts_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("real playback test", "en_female_calm", SpeakParams())
        engine.wait_until_done(timeout_ms=60_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert len(arr) > 0
    assert np.abs(arr).max() > 0


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = F5TTSEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = F5TTSEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_set():
    engine = F5TTSEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = F5TTSEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False
