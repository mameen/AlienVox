"""Manage Voices dialog — enable/disable individual voices and preview them.

Reactive View in the MVC split: reads AppState.stacks / live_voices_for /
is_voice_enabled, and calls AppController.set_voice_enabled /
preview_voice_async. Mirrors the exact stack -> model -> voice hierarchy
AlienVoxTray._rebuild_voice_menu already builds for its Voice ▸ menu, just
rendered as a checkable tree instead of a nested context menu, so both
surfaces agree on structure.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
        self.setWindowTitle("Manage Voices")
        self.resize(560, 480)

        self._state = state
        self._controller = controller
        # Guards _on_item_changed while _populate() is setting initial
        # check states — those setCheckState calls fire itemChanged too,
        # and without this we'd call set_voice_enabled for every row on
        # every open, redundantly (harmless since the setter no-ops on
        # unchanged values, but noisy and wrong to treat as user input).
        self._populating = False

        root = QVBoxLayout(self)

        hint = QLabel(
            "Uncheck a voice to hide it from the voice dropdowns and the tray's Voice menu. "
            "Click ▶ to hear a sample with that voice."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Voice", ""])
        self._tree.setColumnWidth(0, 400)
        self._tree.itemChanged.connect(self._on_item_changed)
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
        self._populating = True
        self._tree.clear()
        for stack in self._state.stacks:
            if not stack.available:
                continue
            stack_item = QTreeWidgetItem([stack.name, ""])
            stack_item.setFlags(stack_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self._tree.addTopLevelItem(stack_item)

            if stack.models:
                # ML-style: Stack -> Models -> Voices (matches tray's 4-level menu)
                for model in stack.models:
                    model_item = QTreeWidgetItem([model.name, ""])
                    model_item.setFlags(model_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                    stack_item.addChild(model_item)
                    for v in model.voices:
                        self._add_voice_row(model_item, stack.id, model.id, v)
            else:
                # SAPI-style: Stack -> Voices, sourced from live_voices
                # (enumerated at runtime, same as the tray menu's source).
                for v in self._state.live_voices_for(stack.id):
                    self._add_voice_row(stack_item, stack.id, "", v)

        self._tree.expandAll()
        self._populating = False

    def _add_voice_row(self, parent_item: QTreeWidgetItem, stack_id: str, model_id: str, voice: dict) -> None:
        voice_id = voice["id"]
        label = voice.get("label", voice_id)

        item = QTreeWidgetItem([label, ""])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled = self._state.is_voice_enabled(stack_id, model_id, voice_id)
        item.setCheckState(0, Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        item.setData(0, _VOICE_ROW_ROLE, (stack_id, model_id, voice_id))
        parent_item.addChild(item)

        preview_btn = QPushButton("▶")
        preview_btn.setFixedWidth(28)
        preview_btn.setToolTip(f"Preview {label}")
        preview_btn.clicked.connect(
            lambda _checked=False, s=stack_id, m=model_id, v=voice_id:
                self._controller.preview_voice_async(s, m, v)
        )
        self._tree.setItemWidget(item, 1, preview_btn)

    # ── User input ────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._populating or column != 0:
            return
        data = item.data(0, _VOICE_ROW_ROLE)
        if data is None:
            return  # a stack/model row (not checkable), not a voice row
        stack_id, model_id, voice_id = data
        enabled = item.checkState(0) == Qt.CheckState.Checked
        self._controller.set_voice_enabled(stack_id, model_id, voice_id, enabled)
