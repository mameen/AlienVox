"""Tests for OuteTTSEngine — no network, no audio hardware required."""
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
)

from .conftest import requires_gpu

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


# ── Voice validation guard ────────────────────────────────────────────────────

def _make_mock_interface(audio: np.ndarray):
    """Return a mock InterfaceHF whose generate() returns a ModelOutput-like object.

    Real ModelOutput.audio is a torch.Tensor shaped [batch, samples]; mocked
    with an actual tensor here since _synthesize_array() calls
    .detach().cpu().numpy() on it.
    """
    import torch
    output = MagicMock()
    output.audio = torch.from_numpy(audio).unsqueeze(0)  # shape (1, N)
    mock_iface = MagicMock()
    mock_iface.generate.return_value = output
    mock_iface.load_default_speaker.return_value = MagicMock()
    return mock_iface


def test_invalid_voice_falls_back_to_default():
    audio = np.zeros(100, dtype=np.float32)
    mock_iface = _make_mock_interface(audio)
    engine = OuteTTSEngine()
    OuteTTSEngine._interface = mock_iface

    with patch("src.engines.outetts_engine.play_audio"):
        engine.speak("hello", "bad_voice", SpeakParams())
        engine.wait_until_done(timeout_ms=15_000)

    mock_iface.load_default_speaker.assert_called_once_with(name=_VOICE_TO_SPEAKER[_DEFAULT_VOICE])


def test_valid_voice_passed_to_speaker_loader():
    """Our short voice IDs must be translated to outetts's real speaker names
    (language-prefixed, e.g. en_female_1) — see _VOICE_TO_SPEAKER."""
    audio = np.zeros(100, dtype=np.float32)
    mock_iface = _make_mock_interface(audio)
    engine = OuteTTSEngine()
    OuteTTSEngine._interface = mock_iface

    with patch("src.engines.outetts_engine.play_audio"):
        engine.speak("hello", "female_1", SpeakParams())
        engine.wait_until_done(timeout_ms=15_000)

    mock_iface.load_default_speaker.assert_called_once_with(name="en_female_1")


# ── speak + play ──────────────────────────────────────────────────────────────

def test_speak_calls_play_audio():
    audio = np.ones(2400, dtype=np.float32)
    mock_iface = _make_mock_interface(audio)
    engine = OuteTTSEngine()
    OuteTTSEngine._interface = mock_iface

    played = []
    with patch("src.engines.outetts_engine.play_audio",
               side_effect=lambda a, r: played.append((a, r))):
        engine.speak("test", "male_1", SpeakParams(volume=50))
        engine.wait_until_done(timeout_ms=15_000)

    assert len(played) == 1
    arr, rate = played[0]
    assert rate == _SAMPLE_RATE
    assert abs(arr[0] - 0.5) < 0.01


def test_int16_audio_normalised_to_float():
    """int16-range audio (max > 1.0) must be normalised before playback."""
    audio_int16 = np.full(100, 16384, dtype=np.float32)  # simulates int16 range
    mock_iface = _make_mock_interface(audio_int16)
    engine = OuteTTSEngine()
    OuteTTSEngine._interface = mock_iface

    played = []
    with patch("src.engines.outetts_engine.play_audio",
               side_effect=lambda a, r: played.append(a)):
        engine.speak("test", "male_1", SpeakParams(volume=100))
        engine.wait_until_done(timeout_ms=15_000)

    assert len(played) == 1
    assert played[0].max() <= 1.0


def test_speak_empty_text_does_nothing():
    engine = OuteTTSEngine()
    OuteTTSEngine._interface = MagicMock()
    with patch("src.engines.outetts_engine.play_audio") as mock_play:
        engine.speak("", "male_1", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


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
