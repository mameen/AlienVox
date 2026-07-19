"""Tests for the stack registry (reads stacks.yaml, checks weights on disk)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.engines.registry import available_stacks, get_stack, StackInfo, ModelInfo


# ── Catalog reading ───────────────────────────────────────────────────────────

def test_returns_all_stacks(stacks_yaml, models_root):
    stacks = available_stacks(stacks_yaml, models_root)
    ids = [s.id for s in stacks]
    assert "sapi5" in ids
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

def test_ml_models_unavailable_when_no_weights(stacks_yaml, models_root):
    # models_root fixture has no subdirs — weights missing
    stacks = available_stacks(stacks_yaml, models_root)
    ml = next(s for s in stacks if s.id == "ml")
    assert ml.available is False
    for m in ml.models:
        assert m.available is False


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


# ── get_stack helper ──────────────────────────────────────────────────────────

def test_get_stack_returns_correct_info(stacks_yaml, models_root):
    info = get_stack("sapi5", stacks_yaml, models_root)
    assert info is not None
    assert info.id == "sapi5"


def test_get_stack_none_for_unknown(stacks_yaml, models_root):
    assert get_stack("nosuchstack", stacks_yaml, models_root) is None
