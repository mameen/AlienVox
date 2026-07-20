"""Tests for F5TTSEngine — no network, no audio hardware required."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.engines.base import SpeakParams
from src.engines.f5tts_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _VALID_VOICE_IDS,
    F5TTSEngine,
)

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


# ── Voice validation guard ────────────────────────────────────────────────────

def _make_mock_model(audio: np.ndarray, sr: int = _SAMPLE_RATE):
    mock = MagicMock()
    mock.infer.return_value = (audio, sr, None)
    return mock


def test_invalid_voice_falls_back_to_default(tmp_path):
    audio = np.zeros(100, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = F5TTSEngine()
    F5TTSEngine._model = mock_model

    # Provide reference files for the default voice
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / f"{_DEFAULT_VOICE}.wav").write_bytes(b"fake")
    (voices_dir / f"{_DEFAULT_VOICE}.txt").write_text("ref text", encoding="utf-8")

    with patch("src.engines.f5tts_engine._ref_wav", return_value=voices_dir / f"{_DEFAULT_VOICE}.wav"), \
         patch("src.engines.f5tts_engine._ref_txt", return_value=voices_dir / f"{_DEFAULT_VOICE}.txt"), \
         patch("src.engines.f5tts_engine.play_audio"):
        engine.speak("hello", "bad_voice", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    # infer() must have been called (invalid voice fell back to default)
    mock_model.infer.assert_called_once()


def test_missing_reference_file_logs_error_and_skips(tmp_path):
    """If the .wav reference is missing, synthesis must be skipped (no crash)."""
    mock_model = _make_mock_model(np.zeros(100, dtype=np.float32))
    engine = F5TTSEngine()
    F5TTSEngine._model = mock_model

    missing_wav = tmp_path / "nonexistent.wav"

    with patch("src.engines.f5tts_engine._ref_wav", return_value=missing_wav), \
         patch("src.engines.f5tts_engine.play_audio") as mock_play:
        engine.speak("hello", _DEFAULT_VOICE, SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    mock_play.assert_not_called()
    mock_model.infer.assert_not_called()


# ── speak + play ──────────────────────────────────────────────────────────────

def test_speak_calls_play_audio(tmp_path):
    audio = np.ones(2400, dtype=np.float32)
    mock_model = _make_mock_model(audio)
    engine = F5TTSEngine()
    F5TTSEngine._model = mock_model

    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    wav_path = voices_dir / f"{_DEFAULT_VOICE}.wav"
    txt_path = voices_dir / f"{_DEFAULT_VOICE}.txt"
    wav_path.write_bytes(b"fake")
    txt_path.write_text("reference text", encoding="utf-8")

    played = []
    with patch("src.engines.f5tts_engine._ref_wav", return_value=wav_path), \
         patch("src.engines.f5tts_engine._ref_txt", return_value=txt_path), \
         patch("src.engines.f5tts_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("test", _DEFAULT_VOICE, SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert abs(arr[0] - 0.5) < 0.01


def test_speak_empty_text_does_nothing():
    engine = F5TTSEngine()
    F5TTSEngine._model = MagicMock()
    with patch("src.engines.f5tts_engine.play_audio") as mock_play:
        engine.speak("", _DEFAULT_VOICE, SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


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
