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

Now that MainWindow is a reactive View over AppState/AppController (see
app_state.py/app_controller.py), these tests build a real AppState and a
minimal fake AppController (fake because a real one loads real engines —
these tests only exercise widget construction, not engine plumbing).

Requires a real QApplication (PySide6 widgets can't be constructed
without one) but builds against fixture data, no real engines/weights.
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from src.model.app_state import AppState
from src.engines.registry import ModelInfo, StackInfo
from src.view.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class _FakeController:
    """Mimics AppController's public surface against a real AppState,
    without loading any real engine — sufficient for testing that
    MainWindow reads/writes AppState correctly."""

    engine = None

    def __init__(self, state: AppState) -> None:
        self.state = state

    def select_voice(self, voice_id: str) -> None:
        self.state.set_voice(voice_id)

    def select_model(self, model_id: str, voice_id: str = "") -> None:
        self.state.set_active_model(model_id)
        if voice_id:
            self.state.set_voice(voice_id)

    def select_stack(self, stack_id: str, voice_id: str = "") -> None:
        self.state.set_active_stack(stack_id)
        if voice_id:
            self.state.set_voice(voice_id)

    def update_params(self, **kwargs) -> None:
        self.state.set_params(**kwargs)

    def build_current_speak_params(self):
        return None


def _ml_stack() -> StackInfo:
    """Fixture stack with two models — order matters: kokoro is listed
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


def _make_state(stacks: list[StackInfo], *, engine: str, model: str, voice: str) -> AppState:
    cfg = {
        "engine": engine, "model": model, "voice": voice,
        "rate": 0, "pitch": 0, "volume": 100,
        "hotkey": "<ctrl>+<esc>", "ttl_seconds": 30,
    }
    return AppState(stacks, cfg)


def _voice_and_model_combo(window: MainWindow, stack_id: str):
    model_combo = next(c for c, sid in window._model_combos if sid == stack_id)
    voice_combo = next(c for c, sid in window._voice_combos if sid == stack_id)
    return model_combo, voice_combo


def test_active_model_selected_not_first_catalog_entry(qapp):
    """With chatterbox active (not kokoro, which is listed first), the
    model dropdown must show chatterbox and the voice dropdown must show
    chatterbox's voices — not silently default to kokoro's."""
    state = _make_state([_ml_stack()], engine="ml", model="chatterbox", voice="default")
    window = MainWindow(state, _FakeController(state))
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
    state = _make_state([_ml_stack()], engine="ml", model="chatterbox", voice="female_calm")
    window = MainWindow(state, _FakeController(state))
    try:
        _, voice_combo = _voice_and_model_combo(window, "ml")
        assert voice_combo.itemData(voice_combo.currentIndex()) == "female_calm"
    finally:
        window.close()


def test_defaults_to_first_model_when_active_model_unknown(qapp):
    """If active_model doesn't match any catalog entry (e.g. empty, or a
    model that got removed), fall back to the first one rather than
    crashing or showing nothing."""
    state = _make_state([_ml_stack()], engine="ml", model="nonexistent-model", voice="")
    window = MainWindow(state, _FakeController(state))
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        assert model_combo.itemData(model_combo.currentIndex()) == "kokoro"
        voice_ids = {voice_combo.itemData(i) for i in range(voice_combo.count())}
        assert voice_ids == {"af_heart", "af_bella"}
    finally:
        window.close()


def test_non_active_stack_ignores_current_voice_id(qapp):
    """AppState.voice belongs to the active stack only — a stack that
    isn't active shouldn't try to match it against its own voice list."""
    stacks = [
        _ml_stack(),
        StackInfo(id="sapi5", name="SAPI 5", available=True, models=[]),
    ]
    # sapi5 is active, not ml — "female_calm" coincidentally matches a
    # chatterbox voice id, but ml shouldn't try to select it since ml isn't
    # the active stack.
    state = _make_state(stacks, engine="sapi5", model="", voice="female_calm")
    window = MainWindow(state, _FakeController(state))
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        assert model_combo.itemData(model_combo.currentIndex()) == "kokoro"
        assert voice_combo.itemData(voice_combo.currentIndex()) == "af_heart"
    finally:
        window.close()


def test_model_combo_change_updates_state_and_reflects_in_voice_combo(qapp):
    """Reactive round-trip: changing the model combo calls the controller,
    which mutates AppState, whose model_changed signal repopulates the
    voice combo — this is the structural fix for the reported bug, not
    just a snapshot at construction time."""
    state = _make_state([_ml_stack()], engine="ml", model="kokoro", voice="af_heart")
    window = MainWindow(state, _FakeController(state))
    try:
        model_combo, voice_combo = _voice_and_model_combo(window, "ml")
        idx = model_combo.findData("chatterbox")
        model_combo.setCurrentIndex(idx)

        assert state.active_model == "chatterbox"
        voice_ids = {voice_combo.itemData(i) for i in range(voice_combo.count())}
        assert voice_ids == {"default", "female_calm"}
    finally:
        window.close()
