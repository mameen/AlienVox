"""Settings dialog — enable/disable individual voices and preview them.

Reactive View in the MVC split: reads AppState.stacks / live_voices_for /
is_voice_enabled, and calls AppController.set_voice_enabled /
preview_voice_async. Mirrors the exact stack -> model -> voice hierarchy
AlienVoxTray._rebuild_voice_menu already builds for its Voice ▸ menu, just
rendered as an expandable tree instead of a nested context menu, so both
surfaces agree on structure.

Per-voice enable/disable is a checkable toggle button (same widget style
as the toolbar's old ✨ enhance toggle), not a tree-item checkbox or a
QRadioButton — each voice is independently on/off, multiple voices per
model can be enabled at once.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..control.app_controller import AppController
from ..model.app_state import AppState

_VOICE_ROW_ROLE = Qt.ItemDataRole.UserRole


class ManageVoicesDialog(QDialog):
    def __init__(self, state: AppState, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(600, 480)

        self._state = state
        self._controller = controller

        root = QVBoxLayout(self)

        hint = QLabel(
            "Toggle a voice off to hide it from the voice dropdowns and the tray's Voice menu. "
            "Click ▶ to hear a sample with that voice."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Voice", "Enabled", ""])
        self._tree.setColumnWidth(0, 380)
        self._tree.setColumnWidth(1, 70)
        root.addWidget(self._tree, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._populate()

    # ── Population ────────────────────────────────────────────────────────

    def _populate(self) -> None:
        self._tree.clear()
        for stack in self._state.stacks:
            if not stack.available:
                continue
            stack_item = QTreeWidgetItem([stack.name, "", ""])
            self._tree.addTopLevelItem(stack_item)

            if stack.models:
                # ML-style: Stack -> Models -> Voices (matches tray's 4-level menu)
                for model in stack.models:
                    model_item = QTreeWidgetItem([model.name, "", ""])
                    stack_item.addChild(model_item)
                    for v in model.voices:
                        self._add_voice_row(model_item, stack.id, model.id, v)
            else:
                # SAPI-style: Stack -> Voices, sourced from live_voices
                # (enumerated at runtime, same as the tray menu's source).
                for v in self._state.live_voices_for(stack.id):
                    self._add_voice_row(stack_item, stack.id, "", v)

        self._tree.expandAll()

    def _add_voice_row(self, parent_item: QTreeWidgetItem, stack_id: str, model_id: str, voice: dict) -> None:
        voice_id = voice["id"]
        label = voice.get("label", voice_id)

        item = QTreeWidgetItem([label, "", ""])
        item.setData(0, _VOICE_ROW_ROLE, (stack_id, model_id, voice_id))
        parent_item.addChild(item)

        enabled = self._state.is_voice_enabled(stack_id, model_id, voice_id)
        toggle_btn = QToolButton()
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(enabled)
        toggle_btn.setText("On" if enabled else "Off")
        toggle_btn.setFixedWidth(48)
        toggle_btn.setToolTip(f"Enable/disable {label}")
        toggle_btn.toggled.connect(
            lambda checked, btn=toggle_btn, s=stack_id, m=model_id, v=voice_id:
                self._on_voice_toggled(btn, s, m, v, checked)
        )
        self._tree.setItemWidget(item, 1, toggle_btn)

        preview_btn = QPushButton("▶")
        preview_btn.setFixedWidth(28)
        preview_btn.setToolTip(f"Preview {label}")
        preview_btn.clicked.connect(
            lambda _checked=False, s=stack_id, m=model_id, v=voice_id:
                self._controller.preview_voice_async(s, m, v)
        )
        self._tree.setItemWidget(item, 2, preview_btn)

    # ── User input ────────────────────────────────────────────────────────

    def _on_voice_toggled(
        self, btn: QToolButton, stack_id: str, model_id: str, voice_id: str, checked: bool
    ) -> None:
        btn.setText("On" if checked else "Off")
        self._controller.set_voice_enabled(stack_id, model_id, voice_id, checked)
