"""Tests for PiperEngine parameter handling.

_synthesize()/_play_wav() ultimately depend on the piper-tts package and
weights on disk, neither of which are available in CI. These tests instead
target the pieces that are pure functions of SpeakParams — the actual
parameter-coverage gap this file exists to close:

  1. Piper-specific extra controls (noise_scale, noise_w, sentence_silence)
     declared in stacks.yaml were never wired from SpeakParams into Piper's
     synthesis config — piper_config_from_params() is the fix, tested here.
  2. Piper never applied `volume` to played audio, unlike every other
     engine — _play_wav()'s scaling is tested here in isolation.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.piper_win import PiperEngine, piper_config_from_params


# ── piper_config_from_params: defaults ──────────────────────────────────────

def test_config_uses_defaults_when_extra_empty():
    cfg = piper_config_from_params(SpeakParams())
    assert cfg == {"noise_scale": 0.667, "noise_w": 0.8, "sentence_silence": 0.2}


# ── piper_config_from_params: overrides flow through ────────────────────────

def test_config_honors_noise_scale_override():
    cfg = piper_config_from_params(SpeakParams(extra={"noise_scale": 0.9}))
    assert cfg["noise_scale"] == 0.9
    # Unset keys still fall back to defaults
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


# ── _play_wav volume scaling ──────────────────────────────────────────────────

def _make_wav_bytes(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Build minimal 44-byte-header mono 16-bit PCM WAV bytes for testing."""
    pcm = samples.astype("<i2").tobytes()
    header = bytearray(44)
    header[0:4] = b"RIFF"
    header[8:12] = b"WAVE"
    header[12:16] = b"fmt "
    header[16:20] = (16).to_bytes(4, "little")
    header[20:22] = (1).to_bytes(2, "little")   # PCM
    header[22:24] = (1).to_bytes(2, "little")   # mono
    header[24:28] = sample_rate.to_bytes(4, "little")
    header[34:36] = (16).to_bytes(2, "little")  # bits per sample
    header[36:40] = b"data"
    header[40:44] = len(pcm).to_bytes(4, "little")
    return bytes(header) + pcm


def test_play_wav_full_volume_plays_unscaled(monkeypatch):
    played = {}

    class FakeSd:
        @staticmethod
        def play(arr, rate):
            played["arr"] = arr
            played["rate"] = rate

        @staticmethod
        def wait():
            pass

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSd)

    engine = PiperEngine()
    samples = np.array([16384, -16384, 0], dtype="<i2")  # 0.5, -0.5, 0.0 as float32
    wav = _make_wav_bytes(samples)
    engine._play_wav(wav, volume=100)

    assert played["arr"] == pytest.approx([0.5, -0.5, 0.0], abs=1e-3)


def test_play_wav_half_volume_scales_audio(monkeypatch):
    played = {}

    class FakeSd:
        @staticmethod
        def play(arr, rate):
            played["arr"] = arr

        @staticmethod
        def wait():
            pass

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSd)

    engine = PiperEngine()
    samples = np.array([16384, -16384], dtype="<i2")
    wav = _make_wav_bytes(samples)
    engine._play_wav(wav, volume=50)

    assert played["arr"] == pytest.approx([0.25, -0.25], abs=1e-3)


def test_play_wav_zero_volume_is_silent(monkeypatch):
    played = {}

    class FakeSd:
        @staticmethod
        def play(arr, rate):
            played["arr"] = arr

        @staticmethod
        def wait():
            pass

    monkeypatch.setitem(__import__("sys").modules, "sounddevice", FakeSd)

    engine = PiperEngine()
    samples = np.array([16384, -16384], dtype="<i2")
    wav = _make_wav_bytes(samples)
    engine._play_wav(wav, volume=0)

    assert played["arr"] == pytest.approx([0.0, 0.0], abs=1e-3)


def test_play_wav_default_volume_is_100():
    """_play_wav's volume parameter defaults to 100 (unscaled) if not passed."""
    import inspect
    sig = inspect.signature(PiperEngine._play_wav)
    assert sig.parameters["volume"].default == 100
