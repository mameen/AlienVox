"""Tests for main.py's SpeakParams construction.

Covers the wiring gap where Piper-specific controls (noise_scale, noise_w,
sentence_silence) declared in stacks.yaml were built into the effective
config but never forwarded into SpeakParams passed to engine.speak().
"""
from __future__ import annotations

from src.main import build_speak_params


def test_base_params_always_populated():
    params = build_speak_params({"rate": 3, "pitch": -2, "volume": 60}, "kokoro")
    assert params.rate == 3
    assert params.pitch == -2
    assert params.volume == 60


def test_defaults_used_when_cfg_missing_keys():
    params = build_speak_params({}, "kokoro")
    assert params.rate == 0
    assert params.pitch == 0
    assert params.volume == 100


def test_non_piper_models_get_empty_extra():
    params = build_speak_params(
        {"noise_scale": 0.9, "noise_w": 0.1, "sentence_silence": 1.0}, "kokoro"
    )
    assert params.extra == {}


def test_piper_forwards_noise_scale():
    params = build_speak_params({"noise_scale": 0.9}, "piper")
    assert params.extra["noise_scale"] == 0.9


def test_piper_forwards_all_extra_controls():
    cfg = {"rate": 0, "volume": 100, "noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3}
    params = build_speak_params(cfg, "piper")
    assert params.extra == {"noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3}


def test_piper_extra_omits_unset_keys():
    """If cfg doesn't have a piper key set, it's absent from extra (not defaulted here —
    piper_config_from_params applies the actual default)."""
    params = build_speak_params({"noise_scale": 0.5}, "piper")
    assert "noise_w" not in params.extra
    assert "sentence_silence" not in params.extra
