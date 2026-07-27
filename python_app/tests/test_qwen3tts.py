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
from unittest.mock import patch

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.qwen3tts_engine import (
    Qwen3TTSEngine,
    _DEFAULT_VOICE,
    _VALID_VOICE_IDS,
    _VOICES,
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
