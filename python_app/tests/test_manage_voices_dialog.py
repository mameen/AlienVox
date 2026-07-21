"""Tests for ManageVoicesDialog — the tree view mirrors AppState's catalog
and reacts to voice enable/disable checkbox changes.

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


def test_tree_reflects_current_enabled_state(qapp):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state))
    try:
        item = _find_voice_item(dlg, "af_bella")
        assert item.checkState(0) == Qt.CheckState.Checked
    finally:
        dlg.close()


def test_unchecking_item_calls_controller_and_updates_state(qapp):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl)
    try:
        item = _find_voice_item(dlg, "af_bella")
        item.setCheckState(0, Qt.CheckState.Unchecked)
        assert state.is_voice_enabled("ml", "kokoro", "af_bella") is False
    finally:
        dlg.close()


def test_preview_button_calls_controller(qapp):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl)
    try:
        item = _find_voice_item(dlg, "af_bella")
        btn = dlg._tree.itemWidget(item, 1)
        btn.click()
        assert ctrl.previewed == [("ml", "kokoro", "af_bella")]
    finally:
        dlg.close()


def test_stack_and_model_rows_are_not_checkable(qapp):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state))
    try:
        stack_item = dlg._tree.topLevelItem(0)
        model_item = stack_item.child(0)
        assert not (stack_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        assert not (model_item.flags() & Qt.ItemFlag.ItemIsUserCheckable)
    finally:
        dlg.close()
