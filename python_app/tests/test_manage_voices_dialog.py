"""Tests for ManageVoicesDialog — the tree view mirrors AppState's catalog
and reacts to per-voice enable/disable toggle-button changes.

Uses a real AppState and a minimal fake AppController (fake because a real
one loads real engines) — same pattern as test_main_window.py.
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.engines.registry import ModelInfo, StackInfo
from src.model.app_state import AppState
from src.view.manage_voices_dialog import ManageVoicesDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


class _FakeController:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.previewed: list[tuple[str, str, str]] = []

    def set_voice_enabled(self, stack_id, model_id, voice_id, enabled) -> None:
        self.state.set_voice_enabled(stack_id, model_id, voice_id, enabled)

    def preview_voice_async(self, stack_id, model_id, voice_id) -> None:
        self.previewed.append((stack_id, model_id, voice_id))


def _ml_stack() -> StackInfo:
    return StackInfo(
        id="ml", name="ML / AI", available=True,
        models=[
            ModelInfo(id="kokoro", name="Kokoro-82M", available=True, voices=[
                {"id": "af_heart", "label": "AF Heart"},
                {"id": "af_bella", "label": "AF Bella"},
            ]),
        ],
    )


def _make_state(**cfg_overrides) -> AppState:
    cfg = {
        "engine": "ml", "model": "kokoro", "voice": "af_heart",
        "rate": 0, "pitch": 0, "volume": 100,
        "hotkey": "<alt>+<esc>", "ttl_seconds": 30,
    }
    cfg.update(cfg_overrides)
    return AppState([_ml_stack()], cfg)


def _find_voice_item(dlg: ManageVoicesDialog, voice_id: str):
    stack_item = dlg._tree.topLevelItem(0)
    model_item = stack_item.child(0)
    for i in range(model_item.childCount()):
        item = model_item.child(i)
        if item.data(0, Qt.ItemDataRole.UserRole)[2] == voice_id:
            return item
    raise AssertionError(f"voice {voice_id} not found in tree")


def test_toggle_button_reflects_current_enabled_state(qapp):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state))
    try:
        item = _find_voice_item(dlg, "af_bella")
        toggle_btn = dlg._tree.itemWidget(item, 1)
        assert toggle_btn.isChecked() is True
    finally:
        dlg.close()


def test_toggling_off_calls_controller_and_updates_state(qapp):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl)
    try:
        item = _find_voice_item(dlg, "af_bella")
        toggle_btn = dlg._tree.itemWidget(item, 1)
        toggle_btn.click()
        assert state.is_voice_enabled("ml", "kokoro", "af_bella") is False
        assert toggle_btn.isChecked() is False
    finally:
        dlg.close()


def test_preview_button_calls_controller(qapp):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl)
    try:
        item = _find_voice_item(dlg, "af_bella")
        preview_btn = dlg._tree.itemWidget(item, 2)
        preview_btn.click()
        assert ctrl.previewed == [("ml", "kokoro", "af_bella")]
    finally:
        dlg.close()


def test_stack_and_model_rows_have_no_toggle_widget(qapp):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state))
    try:
        stack_item = dlg._tree.topLevelItem(0)
        model_item = stack_item.child(0)
        assert dlg._tree.itemWidget(stack_item, 1) is None
        assert dlg._tree.itemWidget(model_item, 1) is None
    finally:
        dlg.close()
