"""Tests for ManageVoicesDialog — the tree view mirrors AppState's catalog
and reacts to per-voice enable/disable toggle-button changes, plus (folded
in from the old InstallDialog) per-model/per-voice size + Install/Uninstall.

Uses a real AppState and a minimal fake AppController (fake because a real
one loads real engines) — same pattern as test_main_window.py.

Column layout: Name(0) / Size(1) / Enabled(2) / Install(3) / Preview(4).
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
        self.uninstalled_models: list[tuple[str, str]] = []
        self.uninstalled_piper_voices: list[str] = []
        self.refreshed = 0

    def set_voice_enabled(self, stack_id, model_id, voice_id, enabled) -> None:
        self.state.set_voice_enabled(stack_id, model_id, voice_id, enabled)

    def preview_voice_async(self, stack_id, model_id, voice_id) -> None:
        self.previewed.append((stack_id, model_id, voice_id))

    def uninstall_model(self, stack_id, model_id, models_root) -> None:
        self.uninstalled_models.append((stack_id, model_id))

    def uninstall_piper_voice(self, voice_id, models_root) -> None:
        self.uninstalled_piper_voices.append(voice_id)

    def refresh_catalog(self) -> None:
        self.refreshed += 1


def _ml_stack(*, kokoro_present: bool = True, piper_present: bool = False) -> StackInfo:
    return StackInfo(
        id="ml", name="ML / AI", available=True,
        models=[
            ModelInfo(
                id="kokoro", name="Kokoro-82M", available=True,
                weights_present=kokoro_present, approx_size_mb=300,
                voices=[
                    {"id": "af_heart", "label": "AF Heart"},
                    {"id": "af_bella", "label": "AF Bella"},
                ],
            ),
            ModelInfo(
                id="piper", name="Piper", available=True,
                weights_present=False, approx_size_mb=None,
                voices=[
                    {"id": "en_US-lessac-medium", "label": "Lessac", "size_mb": 63},
                ],
            ),
        ],
    )


def _make_state(stack: StackInfo | None = None, **cfg_overrides) -> AppState:
    cfg = {
        "engine": "ml", "model": "kokoro", "voice": "af_heart",
        "rate": 0, "pitch": 0, "volume": 100,
        "hotkey": "<alt>+<esc>", "ttl_seconds": 30,
    }
    cfg.update(cfg_overrides)
    return AppState([stack or _ml_stack()], cfg)


def _find_voice_item(dlg: ManageVoicesDialog, model_id: str, voice_id: str):
    stack_item = dlg._tree.topLevelItem(0)
    for mi in range(stack_item.childCount()):
        model_item = stack_item.child(mi)
        for i in range(model_item.childCount()):
            item = model_item.child(i)
            if item.data(0, Qt.ItemDataRole.UserRole)[2] == voice_id \
                    and item.data(0, Qt.ItemDataRole.UserRole)[1] == model_id:
                return item
    raise AssertionError(f"voice {voice_id} not found in tree")


def _find_model_item(dlg: ManageVoicesDialog, model_id: str):
    stack_item = dlg._tree.topLevelItem(0)
    for mi in range(stack_item.childCount()):
        model_item = stack_item.child(mi)
        if model_item.text(0) in (model_id, "Kokoro-82M", "Piper"):
            # match by known display names used in _ml_stack()
            if (model_id == "kokoro" and model_item.text(0) == "Kokoro-82M") or \
                    (model_id == "piper" and model_item.text(0) == "Piper"):
                return model_item
    raise AssertionError(f"model {model_id} not found in tree")


def test_toggle_button_reflects_current_enabled_state(qapp, tmp_path):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        item = _find_voice_item(dlg, "kokoro", "af_bella")
        toggle_btn = dlg._tree.itemWidget(item, 2)
        assert toggle_btn.isChecked() is True
    finally:
        dlg.close()


def test_toggling_off_calls_controller_and_updates_state(qapp, tmp_path):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl, tmp_path)
    try:
        item = _find_voice_item(dlg, "kokoro", "af_bella")
        toggle_btn = dlg._tree.itemWidget(item, 2)
        toggle_btn.click()
        assert state.is_voice_enabled("ml", "kokoro", "af_bella") is False
        assert toggle_btn.isChecked() is False
    finally:
        dlg.close()


def test_preview_button_calls_controller(qapp, tmp_path):
    state = _make_state()
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl, tmp_path)
    try:
        item = _find_voice_item(dlg, "kokoro", "af_bella")
        preview_btn = dlg._tree.itemWidget(item, 4)
        preview_btn.click()
        assert ctrl.previewed == [("ml", "kokoro", "af_bella")]
    finally:
        dlg.close()


def test_stack_and_model_rows_have_no_enabled_toggle_widget(qapp, tmp_path):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        stack_item = dlg._tree.topLevelItem(0)
        model_item = stack_item.child(0)
        assert dlg._tree.itemWidget(stack_item, 2) is None
        assert dlg._tree.itemWidget(model_item, 2) is None
    finally:
        dlg.close()


# ── Model-level size + Install/Uninstall (shared-weights models) ──────────────

def test_model_row_shows_size_label(qapp, tmp_path):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        model_item = _find_model_item(dlg, "kokoro")
        assert model_item.text(1) == "~300 MB"
    finally:
        dlg.close()


def test_model_row_shows_uninstall_when_present(qapp, tmp_path):
    state = _make_state(_ml_stack(kokoro_present=True))
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        model_item = _find_model_item(dlg, "kokoro")
        btn = dlg._tree.itemWidget(model_item, 3)
        assert btn.text() == "Uninstall"
    finally:
        dlg.close()


def test_model_row_shows_install_when_absent(qapp, tmp_path):
    state = _make_state(_ml_stack(kokoro_present=False))
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        model_item = _find_model_item(dlg, "kokoro")
        btn = dlg._tree.itemWidget(model_item, 3)
        assert btn.text() == "Install"
    finally:
        dlg.close()


def test_uninstall_model_button_asks_confirmation_and_calls_controller(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(
        lambda *a, **k: QMessageBox.StandardButton.Yes
    ))

    state = _make_state(_ml_stack(kokoro_present=True))
    ctrl = _FakeController(state)
    dlg = ManageVoicesDialog(state, ctrl, tmp_path)
    try:
        model_item = _find_model_item(dlg, "kokoro")
        btn = dlg._tree.itemWidget(model_item, 3)
        btn.click()
        assert ctrl.uninstalled_models == [("ml", "kokoro")]
        assert ctrl.refreshed == 1
    finally:
        dlg.close()


# ── Per-voice size + Install/Uninstall (Piper — no shared weights blob) ───────

def test_piper_voice_row_shows_size_and_install(qapp, tmp_path):
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        item = _find_voice_item(dlg, "piper", "en_US-lessac-medium")
        assert item.text(1) == "~63 MB"
        btn = dlg._tree.itemWidget(item, 3)
        assert btn.text() == "Install"
    finally:
        dlg.close()


def test_piper_voice_row_shows_uninstall_when_file_present(qapp, tmp_path):
    piper_dir = tmp_path / "ml" / "piper"
    piper_dir.mkdir(parents=True)
    (piper_dir / "en_US-lessac-medium.onnx").write_bytes(b"x")

    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        item = _find_voice_item(dlg, "piper", "en_US-lessac-medium")
        btn = dlg._tree.itemWidget(item, 3)
        assert btn.text() == "Uninstall"
    finally:
        dlg.close()


def test_kokoro_voice_rows_have_no_own_install_button(qapp, tmp_path):
    """Kokoro shares one weights blob across voices — only the model row
    gets Install/Uninstall, not each voice under it (unlike Piper)."""
    state = _make_state()
    dlg = ManageVoicesDialog(state, _FakeController(state), tmp_path)
    try:
        item = _find_voice_item(dlg, "kokoro", "af_bella")
        assert dlg._tree.itemWidget(item, 3) is None
    finally:
        dlg.close()
