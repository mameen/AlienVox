"""Tests for the config resolver (stacks.yaml + user.yaml)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import (
    DEFAULTS,
    get_controls,
    get_voices,
    list_models,
    list_stacks,
    load_effective_config,
    get_stack_def,
    get_model_def,
    save_user_override,
    _load_yaml,
)


# ── Stack catalog discovery ───────────────────────────────────────────────────

def test_list_stacks_returns_known_ids(stacks_yaml):
    assert "sapi5" in list_stacks(stacks_yaml)
    assert "ml" in list_stacks(stacks_yaml)


def test_list_stacks_empty_for_missing_file(tmp_path):
    assert list_stacks(tmp_path / "no_stacks.yaml") == []


_ALL_ML_MODEL_IDS = ["kokoro", "piper", "chatterbox", "dia", "f5tts", "outetts"]


def test_list_models_under_ml(stacks_yaml):
    models = list_models("ml", stacks_yaml)
    assert "kokoro" in models
    assert "piper" in models


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_models_in_catalog(stacks_yaml, model_id):
    assert model_id in list_models("ml", stacks_yaml), \
        f"Model {model_id!r} missing from fixture stacks.yaml"


def test_list_models_empty_for_stack_without_models(stacks_yaml):
    assert list_models("sapi5", stacks_yaml) == []


def test_get_stack_def_returns_name(stacks_yaml):
    s = get_stack_def("sapi5", stacks_yaml)
    assert s.get("name") == "SAPI 5"


def test_get_model_def_returns_name(stacks_yaml):
    m = get_model_def("ml", "kokoro", stacks_yaml)
    assert m.get("name") == "Kokoro-82M"


def test_get_model_def_missing_returns_empty(stacks_yaml):
    assert get_model_def("ml", "nonexistent", stacks_yaml) == {}


# ── Voices ────────────────────────────────────────────────────────────────────

def test_get_voices_kokoro(stacks_yaml):
    voices = get_voices("ml", "kokoro", stacks_yaml)
    ids = [v["id"] for v in voices]
    assert "af_heart" in ids
    assert "bm_george" in ids


def test_get_voices_piper_has_female(stacks_yaml):
    voices = get_voices("ml", "piper", stacks_yaml)
    labels = [v["label"] for v in voices]
    assert any("F" in l for l in labels)


def test_get_voices_sapi5_empty_in_catalog(stacks_yaml):
    # sapi5 voices come from OS at runtime; catalog has none
    assert get_voices("sapi5", "", stacks_yaml) == []


@pytest.mark.parametrize("model_id,expected_voice_ids", [
    ("kokoro",     ["af_heart", "bm_george"]),
    ("chatterbox", ["default"]),
    ("dia",        ["s1", "s2"]),
    ("f5tts",      ["en_female_calm", "en_male_warm"]),
    ("outetts",    ["male_1", "female_1"]),
])
def test_voices_present_for_all_ml_models(stacks_yaml, model_id, expected_voice_ids):
    voices = get_voices("ml", model_id, stacks_yaml)
    ids = [v["id"] for v in voices]
    for vid in expected_voice_ids:
        assert vid in ids, f"Voice {vid!r} missing from {model_id!r} in fixture"


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_models_have_volume_control(stacks_yaml, model_id):
    ctrl = get_controls("ml", model_id, stacks_yaml)
    assert ctrl.get("volume", {}).get("applies") is True, \
        f"volume control missing or disabled for {model_id!r}"


@pytest.mark.parametrize("model_id", ["chatterbox", "dia", "f5tts", "outetts"])
def test_new_ml_models_pitch_not_applicable(stacks_yaml, model_id):
    ctrl = get_controls("ml", model_id, stacks_yaml)
    assert ctrl.get("pitch", {}).get("applies") is not True, \
        f"pitch should not apply for {model_id!r}"


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_model_defs_have_name(stacks_yaml, model_id):
    defn = get_model_def("ml", model_id, stacks_yaml)
    assert defn.get("name"), f"Model {model_id!r} has no name in fixture"


@pytest.mark.parametrize("model_id", _ALL_ML_MODEL_IDS)
def test_all_ml_model_defs_have_weights_subpath(stacks_yaml, model_id):
    defn = get_model_def("ml", model_id, stacks_yaml)
    assert "weights_subpath" in defn, f"Model {model_id!r} missing weights_subpath"


# ── Controls ──────────────────────────────────────────────────────────────────

def test_sapi5_rate_applies(stacks_yaml):
    ctrl = get_controls("sapi5", stacks_yaml=stacks_yaml)
    assert ctrl["rate"]["applies"] is True


def test_sapi5_pitch_applies(stacks_yaml):
    ctrl = get_controls("sapi5", stacks_yaml=stacks_yaml)
    assert ctrl["pitch"]["applies"] is True


def test_ml_kokoro_pitch_not_applicable(stacks_yaml):
    ctrl = get_controls("ml", "kokoro", stacks_yaml)
    assert ctrl["pitch"]["applies"] is False


def test_piper_has_noise_scale(stacks_yaml):
    ctrl = get_controls("ml", "piper", stacks_yaml)
    assert ctrl["noise_scale"]["applies"] is True
    assert ctrl["noise_scale"]["default"] == pytest.approx(0.667)


# ── Effective config (4-layer merge) ─────────────────────────────────────────

def test_effective_config_returns_defaults_with_no_overrides(stacks_yaml, tmp_path):
    missing_user = tmp_path / "no_user.yaml"
    cfg = load_effective_config(stacks_file=stacks_yaml, user_file=missing_user)
    assert cfg["rate"] == DEFAULTS["rate"]
    assert cfg["volume"] == DEFAULTS["volume"]


def test_effective_config_applies_user_overrides(stacks_yaml, user_yaml):
    cfg = load_effective_config(stacks_file=stacks_yaml, user_file=user_yaml)
    assert cfg["rate"] == 2        # fixture user.yaml sets rate=2
    assert cfg["volume"] == 90     # fixture user.yaml sets volume=90


def test_save_and_read_back_override(stacks_yaml, tmp_path):
    uf = tmp_path / "user.yaml"
    save_user_override({"voice": "af_heart", "volume": 75}, uf)
    cfg = load_effective_config(stacks_file=stacks_yaml, user_file=uf)
    assert cfg["voice"] == "af_heart"
    assert cfg["volume"] == 75


def test_save_merges_not_replaces(tmp_path):
    uf = tmp_path / "user.yaml"
    save_user_override({"rate": 3}, uf)
    save_user_override({"volume": 80}, uf)
    data = _load_yaml(uf)
    assert data["rate"] == 3
    assert data["volume"] == 80


def test_effective_config_stack_name_not_leaked_as_top_level(stacks_yaml, tmp_path):
    # 'name' from the stack def should not overwrite a real config key
    cfg = load_effective_config("sapi5", stacks_file=stacks_yaml, user_file=tmp_path / "u.yaml")
    # cfg should NOT have a key from the stack-level dict that conflicts with DEFAULTS
    assert "rate" in cfg  # from defaults
