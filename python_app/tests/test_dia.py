"""Tests for DiaEngine — no network, no audio hardware required."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.dia_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _TAG,
    _VALID_VOICE_IDS,
    DiaEngine,
)

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_known_voices_in_roster():
    assert "s1" in _VALID_VOICE_IDS
    assert "s2" in _VALID_VOICE_IDS


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = DiaEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_kokoro_voices_not_in_roster():
    for vid in ("af_heart", "default", "en_US-amy-medium"):
        assert vid not in _VALID_VOICE_IDS


# ── Speaker tag mapping ───────────────────────────────────────────────────────

@pytest.mark.parametrize("voice_id,expected_tag", [
    ("s1", "[S1]"),
    ("s2", "[S2]"),
])
def test_speaker_tag_mapping(voice_id, expected_tag):
    assert _TAG[voice_id] == expected_tag


# ── Voice validation + tag injection ─────────────────────────────────────────

def _make_mock_model(audio: np.ndarray):
    mock = MagicMock()
    mock.generate.return_value = audio
    return mock


def _captured_text(mock_model) -> str:
    return mock_model.generate.call_args.args[0]


def test_invalid_voice_falls_back_to_default():
    audio = np.zeros(100, dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(audio)

    with patch("src.engines.dia_engine.play_audio"):
        engine.speak("hello", "bad_voice", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    text = _captured_text(DiaEngine._model)
    assert text.startswith(_TAG[_DEFAULT_VOICE])


def test_s1_tag_prepended():
    audio = np.zeros(100, dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(audio)

    with patch("src.engines.dia_engine.play_audio"):
        engine.speak("hello", "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert _captured_text(DiaEngine._model).startswith("[S1]")


def test_s2_tag_prepended():
    audio = np.zeros(100, dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(audio)

    with patch("src.engines.dia_engine.play_audio"):
        engine.speak("hello", "s2", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert _captured_text(DiaEngine._model).startswith("[S2]")


def test_pre_tagged_text_passes_through_unchanged():
    """Text that already contains speaker tags is not re-wrapped."""
    audio = np.zeros(100, dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(audio)
    input_text = "[S1] Hello. [S2] World."

    with patch("src.engines.dia_engine.play_audio"):
        engine.speak(input_text, "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert _captured_text(DiaEngine._model) == input_text


# ── speak + play ──────────────────────────────────────────────────────────────

def test_speak_calls_play_audio():
    audio = np.ones(4410, dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(audio)
    played = []

    with patch("src.engines.dia_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("test", "s1", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert abs(arr[0] - 0.5) < 0.01


def test_speak_empty_text_does_nothing():
    engine = DiaEngine()
    DiaEngine._model = MagicMock()
    with patch("src.engines.dia_engine.play_audio") as mock_play:
        engine.speak("", "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


def test_stereo_output_converted_to_mono():
    stereo = np.ones((2, 4410), dtype=np.float32)
    engine = DiaEngine()
    DiaEngine._model = _make_mock_model(stereo)
    played = []

    with patch("src.engines.dia_engine.play_audio",
               side_effect=lambda a, r: played.append(a)):
        engine.speak("stereo test", "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    assert played[0].ndim == 1


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = DiaEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = DiaEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_set():
    engine = DiaEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = DiaEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False
