"""Tests for the stack registry (reads stacks.yaml, checks weights on disk)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.engines.registry import available_stacks, get_stack, StackInfo, ModelInfo


# ── Catalog reading ───────────────────────────────────────────────────────────

_ALL_ML_MODEL_IDS = ["kokoro", "piper", "chatterbox", "dia", "f5tts", "outetts"]


def test_returns_all_stacks(stacks_yaml, models_root):
    stacks = available_stacks(stacks_yaml, models_root)
    ids = [s.id for s in stacks]
    assert "sapi5" in ids
    assert "speech_platform" in ids
    assert "ml" in ids


def test_every_stack_has_name(stacks_yaml, models_root):
    for s in available_stacks(stacks_yaml, models_root):
        assert s.name, f"Stack {s.id!r} has no name"


# ── SAPI5 availability ────────────────────────────────────────────────────────

def test_sapi5_available_on_windows(stacks_yaml, models_root):
    stacks = available_stacks(stacks_yaml, models_root)
    sapi = next(s for s in stacks if s.id == "sapi5")
    if sys.platform == "win32":
        assert sapi.available is True
        assert sapi.platform_reason == ""
    else:
        assert sapi.available is False
        assert sapi.platform_reason != ""


# ── ML stack without weights ──────────────────────────────────────────────────

def test_piper_unavailable_when_no_weights(stacks_yaml, models_root):
    # models_root fixture has no subdirs — weights missing.
    # piper has no auto_download, so it must be unavailable without local weights.
    # (auto_download models like kokoro remain available — see
    # test_auto_download_models_always_available below.)
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    piper = next(m for m in ml.models if m.id == "piper")
    assert piper.available is False


# ── ML stack with weights present ─────────────────────────────────────────────

def test_ml_models_available_when_weights_exist(stacks_yaml, models_root_with_weights):
    stacks = available_stacks(stacks_yaml, models_root_with_weights)
    ml = next(s for s in stacks if s.id == "ml")
    kokoro = next(m for m in ml.models if m.id == "kokoro")
    piper  = next(m for m in ml.models if m.id == "piper")
    assert kokoro.available is True
    assert piper.available is True
    assert ml.available is True


def test_models_carry_voice_list(stacks_yaml, models_root_with_weights):
    stacks = available_stacks(stacks_yaml, models_root_with_weights)
    ml = next(s for s in stacks if s.id == "ml")
    kokoro = next(m for m in ml.models if m.id == "kokoro")
    voice_ids = [v["id"] for v in kokoro.voices]
    assert "af_heart" in voice_ids


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_models_present_in_catalog(stacks_yaml, models_root, model_id):
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    model_ids = [m.id for m in ml.models]
    assert model_id in model_ids, f"Model {model_id!r} missing from registry"


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_models_available_when_weights_exist(stacks_yaml, models_root_with_weights, model_id):
    stacks = available_stacks(stacks_yaml, models_root_with_weights)
    ml = next(s for s in stacks if s.id == "ml")
    model = next((m for m in ml.models if m.id == model_id), None)
    assert model is not None, f"Model {model_id!r} not found"
    assert model.available is True, f"Model {model_id!r} should be available with weights"


@pytest.mark.parametrize("model_id", ["piper"])  # only non-auto_download models fail without weights
def test_non_auto_download_models_unavailable_without_weights(stacks_yaml, models_root, model_id):
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    model = next((m for m in ml.models if m.id == model_id), None)
    assert model is not None
    assert model.available is False, \
        f"Model {model_id!r} should be unavailable without weights (no auto_download)"


@pytest.mark.parametrize("model_id", ["kokoro", "chatterbox", "dia", "f5tts", "outetts"])
def test_auto_download_models_always_available(stacks_yaml, models_root, model_id):
    """auto_download: true models are always shown as available (download on first speak)."""
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    model = next((m for m in ml.models if m.id == model_id), None)
    assert model is not None
    assert model.available is True, \
        f"auto_download model {model_id!r} should always be available"


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_models_have_non_empty_voice_list(stacks_yaml, models_root, model_id):
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    model = next((m for m in ml.models if m.id == model_id), None)
    assert model is not None
    assert len(model.voices) > 0, f"Model {model_id!r} has no voices in catalog"


# ── get_stack helper ──────────────────────────────────────────────────────────

def test_get_stack_returns_correct_info(stacks_yaml, models_root):
    info = get_stack("sapi5", stacks_yaml, models_root)
    assert info is not None
    assert info.id == "sapi5"


def test_get_stack_none_for_unknown(stacks_yaml, models_root):
    assert get_stack("nosuchstack", stacks_yaml, models_root) is None
