"""Tests for AppController's build_speak_params — SpeakParams construction.

Covers the wiring gap where Piper-specific controls (noise_scale, noise_w,
sentence_silence) declared in stacks.yaml were built into the effective
config but never forwarded into SpeakParams passed to engine.speak().

build_speak_params moved from main.py into app_controller.py during the
MVC refactor (AppController is now the only thing that constructs
SpeakParams) — it now reads rate/pitch/volume from AppState instead of a
raw cfg dict, with only the model-specific "extra" controls still sourced
from a separate extra_cfg dict.
"""
from __future__ import annotations

from src.control.app_controller import build_speak_params


class _FakeState:
    """Minimal stand-in for AppState exposing only what build_speak_params
    reads — avoids requiring a QApplication for these pure-function tests."""

    def __init__(self, rate=0, pitch=0, volume=100, active_model="kokoro"):
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.active_model = active_model


def test_base_params_always_populated():
    state = _FakeState(rate=3, pitch=-2, volume=60, active_model="kokoro")
    params = build_speak_params(state)
    assert params.rate == 3
    assert params.pitch == -2
    assert params.volume == 60


def test_defaults_used_when_state_has_defaults():
    state = _FakeState(active_model="kokoro")
    params = build_speak_params(state)
    assert params.rate == 0
    assert params.pitch == 0
    assert params.volume == 100


def test_non_piper_models_get_empty_extra():
    state = _FakeState(active_model="kokoro")
    extra_cfg = {"noise_scale": 0.9, "noise_w": 0.1, "sentence_silence": 1.0}
    params = build_speak_params(state, extra_cfg)
    assert params.extra == {}


def test_piper_forwards_noise_scale():
    state = _FakeState(active_model="piper")
    params = build_speak_params(state, {"noise_scale": 0.9})
    assert params.extra["noise_scale"] == 0.9


def test_piper_forwards_all_extra_controls():
    state = _FakeState(active_model="piper")
    extra_cfg = {"noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3}
    params = build_speak_params(state, extra_cfg)
    assert params.extra == {"noise_scale": 0.1, "noise_w": 0.2, "sentence_silence": 0.3}


def test_piper_extra_omits_unset_keys():
    """If extra_cfg doesn't have a piper key set, it's absent from extra
    (not defaulted here — piper_config_from_params applies the actual
    default)."""
    state = _FakeState(active_model="piper")
    params = build_speak_params(state, {"noise_scale": 0.5})
    assert "noise_w" not in params.extra
    assert "sentence_silence" not in params.extra


def test_extra_cfg_none_defaults_to_empty():
    state = _FakeState(active_model="piper")
    params = build_speak_params(state, None)
    assert params.extra == {}
