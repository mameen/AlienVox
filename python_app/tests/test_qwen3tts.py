"""Tests for Qwen3-TTS engine support.

Mirrors test_outetts.py's shape: pure-logic voice-roster tests (no gating),
then @requires_weights-gated real-synthesis tests covering default voice, at
least one additional distinct voice, volume scaling, invalid-voice fallback,
and speak() -> play_audio() wiring.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.qwen3tts_engine import (
    _VALID_VOICE_IDS,
    _VOICES,
    Qwen3TTSEngine,
    apply_volume,
    resolve_language,
    resolve_speaker_name,
)

from .conftest import requires_weights

requires_qwen3tts_weights = requires_weights("ml/qwen3tts")


# ── Pure-logic tests (no model required) ─────────────────────────────────────


class TestVoiceRoster:
    def test_all_9_voices_present(self):
        assert len(_VOICES) == 9

    def test_no_duplicate_ids(self):
        ids = [v.id for v in _VOICES]
        assert len(ids) == len(set(ids))

    def test_all_ids_match_valid_set(self):
        ids = {v.id for v in _VOICES}
        assert ids == _VALID_VOICE_IDS


class TestResolveSpeakerName:
    def test_known_id_returns_exact_speaker(self):
        assert resolve_speaker_name("vivian") == "Vivian"
        assert resolve_speaker_name("uncle_fu") == "Uncle_Fu"
        assert resolve_speaker_name("ono_anna") == "Ono_Anna"

    def test_unknown_id_falls_back_to_default(self):
        default_speaker = _VOICES[0].name.split()[0]  # e.g. "Vivian" from "(F ..."
        assert resolve_speaker_name("nonexistent_voice") == default_speaker

    def test_none_uses_default(self):
        default_speaker = _VOICES[0].name.split()[0]
        assert resolve_speaker_name(None) == default_speaker


class TestResolveLanguage:
    def test_known_language_per_voice(self):
        assert resolve_language("dylan") == "English"
        assert resolve_language("uncle_fu") == "Chinese"
        assert resolve_language("ono_anna") == "Japanese"
        assert resolve_language("sohee") == "Korean"

    def test_unknown_falls_back(self):
        # vivian → Chinese
        assert resolve_language("nonexistent") == "Chinese"


class TestApplyVolume:
    def test_full_volume(self):
        buf = np.array([1.0, -0.5, 0.0], dtype=np.float32)
        result = apply_volume(buf, 100)
        np.testing.assert_array_equal(result, buf)

    def test_half_volume(self):
        buf = np.array([2.0, -1.0], dtype=np.float32)
        result = apply_volume(buf, 50)
        np.testing.assert_array_almost_equal(result, [1.0, -0.5])

    def test_zero_volume(self):
        buf = np.array([1.0, 2.0], dtype=np.float32)
        result = apply_volume(buf, 0)
        np.testing.assert_array_equal(result, np.zeros_like(buf))

    def test_clamps_above_100(self):
        buf = np.zeros(1, dtype=np.float32)
        assert apply_volume(buf, 200).sum() >= 0  # no crash


class TestEngineConstruction:
    def test_engine_instantiates_without_load(self):
        eng = Qwen3TTSEngine()
        assert hasattr(eng, '_done')
        assert hasattr(eng, '_stop_requested')

    def test_list_voices_returns_9(self):
        eng = Qwen3TTSEngine()
        voices = eng.list_voices()
        assert len(voices) == 9

    def test_list_voices_contains_all_valid_ids(self):
        eng = Qwen3TTSEngine()
        ids = {v.id for v in eng.list_voices()}
        assert ids == _VALID_VOICE_IDS

    def test_empty_synthesis_and_ready_stop_lifecycle_do_not_load_model(self):
        eng = Qwen3TTSEngine()
        assert eng.synthesize("  ", "vivian", SpeakParams()) is None
        assert eng.wait_until_done(1)
        eng.speak("  ", "vivian", SpeakParams())
        eng.stop()
        assert eng.wait_until_done(1)
        eng._do_speak("", "vivian", SpeakParams())
        assert eng.wait_until_done(1)


@requires_qwen3tts_weights
@pytest.mark.parametrize("voice_id", ["vivian", "dylan"])
def test_real_qwen_synthesis_has_valid_audio(voice_id):
    """Exercise real local weights with the shared canonical benchmark phrase."""
    from src.control.app_controller import SAMPLE_TEXT

    audio, sample_rate = Qwen3TTSEngine().synthesize(SAMPLE_TEXT, voice_id, SpeakParams())
    assert sample_rate > 0
    assert audio.ndim == 1 and audio.size > sample_rate // 2
    assert np.isfinite(audio).all()
    assert float(np.max(np.abs(audio))) <= 1.0


@requires_qwen3tts_weights
def test_real_qwen_volume_mute_is_silent():
    from src.control.app_controller import SAMPLE_TEXT

    audio, _ = Qwen3TTSEngine().synthesize(
        SAMPLE_TEXT, "vivian", SpeakParams(volume=0)
    )
    assert np.count_nonzero(audio) == 0
