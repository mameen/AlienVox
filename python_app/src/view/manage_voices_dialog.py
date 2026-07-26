"""Settings dialog — enable/disable voices, preview them, and install/
uninstall model weights, all in one place.

Reactive View in the MVC split: reads AppState.stacks / live_voices_for /
is_voice_enabled, and calls AppController.set_voice_enabled /
preview_voice_async / download_model / uninstall_model /
uninstall_piper_voice / refresh_catalog. Mirrors the exact
stack -> model -> voice hierarchy AlienVoxTray._rebuild_voice_menu already
builds for its Voice ▸ menu, just rendered as an expandable tree instead of
a nested context menu, so both surfaces agree on structure.

Folds what used to be a separate InstallDialog into this one (see
docs/issues — install_dialog.py is gone): one dialog to enable/disable a
voice, preview it, see its size, and install/uninstall it, instead of two.

Per-voice enable/disable uses the shared ToggleSwitch widget (same one
the toolbar's global Enhanced toggle uses) — each voice is independently
on/off, multiple voices per model can be enabled at once; not a tree-item
checkbox or a mutually-exclusive QRadioButton group.

Install/uninstall granularity differs by model, driven by
ModelInfo.weights_present (see registry.py):
  - Most ML models (Kokoro, Chatterbox, Dia, F5-TTS, OuteTTS, VibeVoice)
    share ONE weights blob across all their voices — Install/Uninstall is a
    MODEL-level row action; the voice rows under it have no install button
    of their own.
  - Piper has no shared blob — every voice is its own separate .onnx/.json
    download — so Piper's Install/Uninstall is a VOICE-level action instead,
    and its model row shows only a size/status summary, no button.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import logger as _logger_mod
from ..control.app_controller import AppController
from ..engines.registry import ModelInfo
from ..model.app_state import AppState
from .toggle_switch import ToggleSwitch

_log = _logger_mod.get_logger("manage_voices")

_VOICE_ROW_ROLE = Qt.ItemDataRole.UserRole
_ACCENT = "#0078d4"
_LIVE = "#107c10"
_OFFLINE = "#0067b8"

# Piper is the only model without a shared weights blob — see module
# docstring's "Install/uninstall granularity" section.
_PER_VOICE_INSTALL_MODELS = {"piper"}


def _fmt_size_mb(size_mb: float | None) -> str:
    if size_mb is None:
        return ""
    if size_mb >= 1000:
        return f"~{size_mb / 1000:.1f} GB"
    return f"~{size_mb:.0f} MB"


class _DownloadWorker(QObject):
    """Runs download_model() in a background thread; emits signals back to
    the UI thread — same pattern the old install_dialog.py used."""

    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, controller: AppController, stack_id: str, model_id: str,
                 models_root: Path, voice_id: str | None) -> None:
        super().__init__()
        self._controller = controller
        self._stack_id = stack_id
        self._model_id = model_id
        self._models_root = models_root
        self._voice_id = voice_id

    def run(self) -> None:
        try:
            self._controller.download_model(
                self._stack_id, self._model_id, self._models_root,
                on_progress=lambda done, total, desc: self.progress.emit(done, total, desc),
                voice_id=self._voice_id,
            )
            self.finished.emit(True, "Install complete.")
        except Exception as exc:
            _log.error("install failed: %s", exc)
            self.finished.emit(False, str(exc))


class ManageVoicesDialog(QDialog):
    def __init__(
        self,
        state: AppState,
        controller: AppController,
        models_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(760, 520)

        self._state = state
        self._controller = controller
        self._models_root = models_root
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None

        root = QVBoxLayout(self)

        hint = QLabel(
            "Toggle a voice off to hide it from the voice dropdowns and the tray's Voice menu. "
            "Click ▶ to hear a sample. Install/Uninstall a model (or, for Piper, a single voice) "
            "to control what's actually downloaded on this machine."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(hint)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(["Name", "Size", "Enabled", "Install", "Preview"])
        self._tree.setColumnWidth(0, 320)
        self._tree.setColumnWidth(1, 80)
        self._tree.setColumnWidth(2, 70)
        self._tree.setColumnWidth(3, 90)
        self._tree.setStyleSheet("QTreeView::item { min-height: 30px; }")
        root.addWidget(self._tree, stretch=1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid #ccc; border-radius: 4px; text-align: center; height: 18px; font-size: 11px; }}
            QProgressBar::chunk {{ background: {_ACCENT}; border-radius: 3px; }}
        """)
        self._progress_bar.hide()
        root.addWidget(self._progress_bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px; color:#555;")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        root.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._state.catalog_changed.connect(self._populate)
        self._populate()

    # ── Population ────────────────────────────────────────────────────────

    def _populate(self) -> None:
        self._tree.clear()
        for stack in self._state.stacks:
            if not stack.available:
                continue
            stack_item = QTreeWidgetItem([stack.name, "", "", "", ""])
            self._tree.addTopLevelItem(stack_item)

            if stack.models:
                # ML-style: Stack -> Models -> Voices (matches tray's 4-level menu)
                for model in stack.models:
                    model_item = QTreeWidgetItem([model.name, "", "", "", ""])
                    stack_item.addChild(model_item)
                    if model.id not in _PER_VOICE_INSTALL_MODELS:
                        self._add_model_size_and_install(model_item, stack.id, model)
                    for v in model.voices:
                        self._add_voice_row(model_item, stack.id, model.id, v, model)
            else:
                # SAPI-style: Stack -> Voices, sourced from live_voices
                # (enumerated at runtime, same as the tray menu's source).
                for v in self._state.live_voices_for(stack.id):
                    self._add_voice_row(stack_item, stack.id, "", v, None)

        self._tree.expandAll()

    def _add_model_size_and_install(self, model_item: QTreeWidgetItem, stack_id: str, model: ModelInfo) -> None:
        model_item.setText(1, _fmt_size_mb(model.approx_size_mb))

        btn = QPushButton("Uninstall" if model.weights_present else "Install")
        btn.setFixedWidth(80)
        btn.setStyleSheet("font-size:11px; padding:2px;")
        if model.weights_present:
            btn.clicked.connect(lambda _c=False, s=stack_id, m=model.id: self._confirm_uninstall_model(s, m))
        else:
            btn.clicked.connect(lambda _c=False, s=stack_id, m=model.id: self._start_install(s, m))
        self._tree.setItemWidget(model_item, 3, btn)

    def _add_voice_row(
        self, parent_item: QTreeWidgetItem, stack_id: str, model_id: str,
        voice: dict, model: ModelInfo | None,
    ) -> None:
        voice_id = voice["id"]
        label = voice.get("label", voice_id)

        item = QTreeWidgetItem([label, "", "", "", ""])
        item.setData(0, _VOICE_ROW_ROLE, (stack_id, model_id, voice_id))
        parent_item.addChild(item)

        enabled = self._state.is_voice_enabled(stack_id, model_id, voice_id)
        toggle = ToggleSwitch()
        toggle.setChecked(enabled)
        toggle.setToolTip(f"Enable/disable {label}")
        toggle.toggled.connect(
            lambda checked, s=stack_id, m=model_id, v=voice_id:
                self._controller.set_voice_enabled(s, m, v, checked)
        )
        self._tree.setItemWidget(item, 2, toggle)

        # Per-voice size + Install/Uninstall — only for models with no
        # shared weights blob (Piper today). Every other model's voices
        # are covered by their parent model row's button instead.
        if model_id in _PER_VOICE_INSTALL_MODELS:
            size_mb = voice.get("size_mb")
            item.setText(1, _fmt_size_mb(size_mb))
            voice_path = self._models_root / "ml" / model_id / f"{voice_id}.onnx"
            present = voice_path.exists()
            btn = QPushButton("Uninstall" if present else "Install")
            btn.setFixedWidth(80)
            btn.setStyleSheet("font-size:11px; padding:2px;")
            if present:
                btn.clicked.connect(lambda _c=False, v=voice_id: self._confirm_uninstall_piper_voice(v, label))
            else:
                btn.clicked.connect(
                    lambda _c=False, s=stack_id, m=model_id, v=voice_id:
                        self._start_install(s, m, voice_id=v)
                )
        preview_cell = QWidget()
        preview_layout = QHBoxLayout(preview_cell)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(4)

        sample_path = self._controller.sample_asset_path(stack_id, model_id, voice_id)
        live_available = bool(model and model.weights_present)

        if live_available:
            live_btn = QPushButton("Live")
            live_btn.setFixedWidth(52)
            live_btn.setToolTip(f"Play a live preview of {label}")
            live_btn.setStyleSheet(
                "font-size:11px; padding:2px 6px; color:white; background:#107c10; border:none; border-radius:3px;"
            )
            live_btn.clicked.connect(
                lambda _checked=False, s=stack_id, m=model_id, v=voice_id:
                    self._controller.preview_voice_async(s, m, v)
            )
            preview_layout.addWidget(live_btn)

        if sample_path and sample_path.exists():
            sample_btn = QPushButton("Sample")
            sample_btn.setFixedWidth(62)
            sample_btn.setToolTip(f"Play the bundled offline sample for {label}")
            sample_btn.setStyleSheet(
                "font-size:11px; padding:2px 6px; color:white; background:#0067b8; border:none; border-radius:3px;"
            )
            sample_btn.clicked.connect(
                lambda _checked=False, s=stack_id, m=model_id, v=voice_id:
                    self._controller.preview_sample_async(s, m, v)
            )
            preview_layout.addWidget(sample_btn)

        preview_layout.addStretch()
        self._tree.setItemWidget(item, 4, preview_cell)

    # ── Install ───────────────────────────────────────────────────────────

    def _start_install(self, stack_id: str, model_id: str, voice_id: str | None = None) -> None:
        if self._thread is not None:
            self._status_lbl.setText("A download is already in progress — wait for it to finish.")
            self._status_lbl.show()
            return

        self._progress_bar.setRange(0, 0)
        self._progress_bar.show()
        self._status_lbl.setText(f"Starting download for {model_id}{'/' + voice_id if voice_id else ''}…")
        self._status_lbl.show()

        self._worker = _DownloadWorker(self._controller, stack_id, model_id, self._models_root, voice_id)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_install_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, done: int, total: int, desc: str) -> None:
        self._status_lbl.setText(desc)
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(done)
        else:
            self._progress_bar.setRange(0, 0)

    def _on_install_finished(self, success: bool, message: str) -> None:
        self._status_lbl.setText(message)
        self._progress_bar.hide()
        self._thread = None
        self._worker = None
        if success:
            self._controller.refresh_catalog()
        else:
            QMessageBox.warning(self, "Install failed", message)

    # ── Uninstall ─────────────────────────────────────────────────────────

    def _confirm_uninstall_model(self, stack_id: str, model_id: str) -> None:
        reply = QMessageBox.question(
            self, "Uninstall model",
            f"Delete {model_id}'s downloaded weights? This removes every voice under it "
            "until it's reinstalled. Model weights only — your enable/disable and other "
            "settings are unaffected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._controller.uninstall_model(stack_id, model_id, self._models_root)
        except Exception as exc:
            QMessageBox.warning(self, "Uninstall failed", str(exc))
            return
        self._controller.refresh_catalog()

    def _confirm_uninstall_piper_voice(self, voice_id: str, label: str) -> None:
        reply = QMessageBox.question(
            self, "Uninstall voice",
            f"Delete the downloaded files for \"{label}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._controller.uninstall_piper_voice(voice_id, self._models_root)
        except Exception as exc:
            QMessageBox.warning(self, "Uninstall failed", str(exc))
            return
        self._controller.refresh_catalog()
