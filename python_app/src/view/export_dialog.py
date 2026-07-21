"""Export Audio dialog — WAV / MP3 with a progress bar.

Usage:
    dlg = ExportDialog(engine, text, voice_id, params, parent=self)
    dlg.exec()
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from ..engines.base import SpeakParams, TtsEngine


class _Worker(QObject):
    progress = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, engine, text, voice_id, params, dest):
        super().__init__()
        self._engine = engine
        self._text = text
        self._voice_id = voice_id
        self._params = params
        self._dest = dest

    def run(self) -> None:
        from ..control.audio_exporter import ExportError, export_audio
        try:
            export_audio(
                self._engine,
                self._text,
                self._voice_id,
                self._params,
                self._dest,
                on_progress=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit()
        except ExportError as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")


class ExportDialog(QDialog):
    """Modal dialog: pick format + path, show synthesis progress, export."""

    def __init__(
        self,
        engine: "TtsEngine",
        text: str,
        voice_id: str,
        params: "SpeakParams",
        default_name: str = "alienvox_export",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Audio")
        self.setMinimumWidth(480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._engine = engine
        self._text = text
        self._voice_id = voice_id
        self._params = params
        self._default_name = default_name
        self._worker: _Worker | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Format row
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItem("WAV  (lossless)", ".wav")
        self._fmt_combo.addItem("MP3  (192 kbps)", ".mp3")
        self._fmt_combo.currentIndexChanged.connect(self._update_path_ext)
        fmt_row.addWidget(self._fmt_combo)
        fmt_row.addStretch()
        root.addLayout(fmt_row)

        # Path row
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Output file path…")
        path_row.addWidget(self._path_edit, stretch=1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        root.addLayout(path_row)

        # Set a sensible default path
        self._update_path_ext()

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_bar.setVisible(False)
        root.addWidget(self._progress_bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px; color:#555;")
        root.addWidget(self._status_lbl)

        # Buttons
        self._buttons = QDialogButtonBox()
        self._export_btn = self._buttons.addButton("Export", QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._export_btn.clicked.connect(self._start_export)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def _current_ext(self) -> str:
        return self._fmt_combo.currentData() or ".wav"

    def _update_path_ext(self) -> None:
        ext = self._current_ext()
        current = self._path_edit.text()
        if current:
            p = Path(current)
            self._path_edit.setText(str(p.with_suffix(ext)))
        else:
            from pathlib import Path as _P
            import os
            default_dir = _P(os.path.expanduser("~/Desktop"))
            self._path_edit.setText(str(default_dir / f"{self._default_name}{ext}"))

    def _browse(self) -> None:
        ext = self._current_ext()
        if ext == ".wav":
            filt = "WAV Audio (*.wav)"
        else:
            filt = "MP3 Audio (*.mp3)"
        start = self._path_edit.text() or ""
        path, _ = QFileDialog.getSaveFileName(self, "Export Audio", start, filt)
        if path:
            p = Path(path)
            if not p.suffix:
                p = p.with_suffix(ext)
            self._path_edit.setText(str(p))

    def _start_export(self) -> None:
        dest_str = self._path_edit.text().strip()
        if not dest_str:
            self._status_lbl.setText("Please choose an output path.")
            return
        if not self._text.strip():
            self._status_lbl.setText("No text to export.")
            return

        dest = Path(dest_str)
        if not dest.suffix:
            dest = dest.with_suffix(self._current_ext())

        self._export_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._status_lbl.setText("Starting…")

        worker = _Worker(self._engine, self._text, self._voice_id, self._params, dest)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)
        self._worker = worker

        thread = threading.Thread(target=worker.run, daemon=True, name="export-audio")
        thread.start()

    def _on_progress(self, msg: str) -> None:
        self._status_lbl.setText(msg)

    def _on_finished(self) -> None:
        self._progress_bar.setVisible(False)
        self._status_lbl.setText(f"Exported: {Path(self._path_edit.text()).name}")
        self._export_btn.setEnabled(True)
        # Auto-close after a moment
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self.accept)

    def _on_error(self, msg: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_lbl.setStyleSheet("font-size:11px; color:#c00;")
        self._status_lbl.setText(f"Error: {msg}")
        self._export_btn.setEnabled(True)
