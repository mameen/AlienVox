"""Tests for MainWindow's voice/model bar construction.

Regression coverage for a bug reported multiple times: the model dropdown
always visually defaulted to stacks.yaml's FIRST catalog model (e.g.
Kokoro), and the voice dropdown was populated from that model's voices —
regardless of which model was actually active (persisted from a prior
session, e.g. Chatterbox). Picking a voice from that mismatched dropdown
only ever updated cfg["voice"] via the voice-only change handler; nothing
detected a model change because the UI never visibly showed one, leaving
cfg["voice"] holding an ID that belongs to a completely different model
than the one actually active (observed in production: "af_bella" — a
Kokoro voice — while Chatterbox stayed the active engine).

Requires a real QApplication (PySide6 widgets can't be constructed
without one) but builds against fixture data, no real engines/weights.
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from src.engines.registry import ModelInfo, StackInfo
from src.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _ml_stack() -> StackInfo:
    """Fixture stack with three models — order matters: kokoro is listed
    FIRST, matching production stacks.yaml, so a naive "always pick
    models[0]" bug would surface as picking kokoro here too."""
    return StackInfo(
        id="ml",
        name="ML / AI",
        available=True,
        models=[
            ModelInfo(id="kokoro", name="Kokoro-82M", available=True, voices=[
                {"id": "af_heart", "label": "American F Heart"},
                {"id": "af_bella", "label": "American F Bella"},
            ]),
            ModelInfo(id="chatterbox", name="Chatterbox 0.5B", available=True, voices=[
                {"id": "default", "label": "Default"},
                {"id": "female_calm", "label": "Female Calm"},
            ]),
        ],
    )


def _voice_and_model_combo(window: MainWindow, stack_id: str):
    model_combo = next(c for c, sid in window._model_combos if sid == stack_id)
    voice_combo = next(c for c, sid in window._voice_combos if sid == stack_id)
    return model_combo, voice_combo


def test_active_model_selected_not_first_catalog_entry(qapp):
    """With chatterbox active (not kokoro, which is listed first), the
    model dropdown must show chatterbox and the voice dropdown must show
    chatterbox's voices — not silently default to kokoro's."""
    window = MainWindow(
        stacks=[_ml_stack()],
        active_stack_id="ml",
        active_model_id="chatterbox",
        current_voice_id="default",
    )
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        assert model_combo.itemData(model_combo.currentIndex()) == "chatterbox"
        voice_ids = {voice_combo.itemData(i) for i in range(voice_combo.count())}
        assert voice_ids == {"default", "female_calm"}
        assert "af_heart" not in voice_ids
        assert "af_bella" not in voice_ids
    finally:
        window.close()


def test_active_voice_selected_within_active_model(qapp):
    window = MainWindow(
        stacks=[_ml_stack()],
        active_stack_id="ml",
        active_model_id="chatterbox",
        current_voice_id="female_calm",
    )
    try:
        _, voice_combo = _voice_and_model_combo(window, "ml")
        assert voice_combo.itemData(voice_combo.currentIndex()) == "female_calm"
    finally:
        window.close()


def test_defaults_to_first_model_when_active_model_unknown(qapp):
    """If active_model_id doesn't match any catalog entry (e.g. empty,
    or a model that got removed), fall back to the first one rather than
    crashing or showing nothing."""
    window = MainWindow(
        stacks=[_ml_stack()],
        active_stack_id="ml",
        active_model_id="nonexistent-model",
        current_voice_id="",
    )
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        assert model_combo.itemData(model_combo.currentIndex()) == "kokoro"
        voice_ids = {voice_combo.itemData(i) for i in range(voice_combo.count())}
        assert voice_ids == {"af_heart", "af_bella"}
    finally:
        window.close()


def test_non_active_stack_ignores_current_voice_id(qapp):
    """current_voice_id belongs to the active stack only — a stack that
    isn't active shouldn't try to match it against its own voice list."""
    stacks = [
        _ml_stack(),
        StackInfo(id="sapi5", name="SAPI 5", available=True, models=[]),
    ]
    window = MainWindow(
        stacks=stacks,
        active_stack_id="sapi5",  # ml is NOT the active stack here
        active_model_id="",
        current_voice_id="female_calm",  # coincidentally a valid chatterbox voice id
    )
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        # ml isn't active, so it should show its first model (kokoro),
        # not try to match "female_calm" against kokoro's voice list.
        assert model_combo.itemData(model_combo.currentIndex()) == "kokoro"
        assert voice_combo.itemData(voice_combo.currentIndex()) == "af_heart"
    finally:
        window.close()
