"""Install Model dialog — downloads model weights / voice files with a progress bar.

Each engine type has a different install strategy:
  - Kokoro:  one HuggingFace repo snapshot (~300 MB) via huggingface_hub
  - Piper:   one .onnx + one .onnx.json per voice from rhasspy/piper-voices (~30–150 MB each)
  - Others:  show a "not yet supported" message

The dialog is non-blocking: download runs on a daemon thread; progress is
pushed back to the Qt main thread via signals (thread-safe).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import logger as _logger_mod
from ..engines.registry import StackInfo

_log = _logger_mod.get_logger("install")

_ACCENT = "#0078d4"

# HuggingFace repo for Piper voices
_PIPER_HF_REPO = "rhasspy/piper-voices"
# Kokoro model repo
_KOKORO_HF_REPO = "hexgrad/Kokoro-82M"


class _DownloadWorker(QObject):
    """Runs in a background thread; emits signals back to the UI thread."""

    progress = Signal(int, int, str)   # (bytes_done, bytes_total, description)
    finished = Signal(bool, str)       # (success, message)

    def __init__(self, task: Callable[[], None]) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            self._task()
            self.finished.emit(True, "Download complete.")
        except Exception as exc:
            _log.error("download failed: %s", exc)
            self.finished.emit(False, str(exc))


class InstallDialog(QDialog):
    """Per-stack model install dialog with a progress bar."""

    def __init__(
        self,
        stack: StackInfo,
        models_root: Path,
        active_model_id: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._stack = stack
        self._models_root = models_root
        self._thread: QThread | None = None
        self._worker: _DownloadWorker | None = None

        # Determine which model the dialog is for — default to first available
        self._active_model_id = active_model_id or (
            stack.models[0].id if stack.models else ""
        )

        self.setWindowTitle(f"Install — {stack.name}")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setMinimumWidth(480)
        self.setModal(True)

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        title = QLabel(f"<b>Install {self._stack.name} Models</b>")
        title.setStyleSheet("font-size:13px;")
        layout.addWidget(title)

        if self._active_model_id == "kokoro":
            self._build_kokoro_ui(layout)
        elif self._active_model_id == "piper":
            self._build_piper_ui(layout)
        else:
            layout.addWidget(QLabel(
                f"Automatic install is not yet supported for '{self._active_model_id}'.\n"
                "Please refer to the documentation for manual setup."
            ))

        # Progress bar (hidden until download starts)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 20px;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background: {_ACCENT};
                border-radius: 3px;
            }}
        """)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px; color:#555;")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        layout.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        self._download_btn = QPushButton("Download")
        self._download_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #005fa3; }}
            QPushButton:disabled {{ background: #aaa; }}
        """)
        self._download_btn.clicked.connect(self._on_download)

        self._close_btn = QPushButton("Close")
        self._close_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px 16px;
                font-size: 12px;
            }
            QPushButton:hover { background: #e8e8e8; }
        """)
        self._close_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(self._download_btn)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _build_kokoro_ui(self, layout: QVBoxLayout) -> None:
        desc = QLabel(
            "Kokoro-82M is a compact, high-quality neural TTS model (~300 MB).\n"
            "It auto-downloads from HuggingFace Hub and includes all voices shown below."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:11px; color:#444;")
        layout.addWidget(desc)

        voices_lbl = QLabel("<b>Included voices:</b>")
        voices_lbl.setStyleSheet("font-size:11px;")
        layout.addWidget(voices_lbl)

        voice_list = QListWidget()
        voice_list.setMaximumHeight(140)
        voice_list.setStyleSheet("font-size:11px;")
        for model in self._stack.models:
            if model.id == "kokoro":
                for v in model.voices:
                    voice_list.addItem(QListWidgetItem(v.get("label", v["id"])))
        layout.addWidget(voice_list)

        self._kokoro_model = next((m for m in self._stack.models if m.id == "kokoro"), None)

    def _build_piper_ui(self, layout: QVBoxLayout) -> None:
        desc = QLabel(
            "Piper downloads individual voice files (~30–150 MB each).\n"
            "Select the voices you want to install:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:11px; color:#444;")
        layout.addWidget(desc)

        self._voice_list = QListWidget()
        self._voice_list.setMaximumHeight(180)
        self._voice_list.setStyleSheet("font-size:11px;")
        self._voice_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for model in self._stack.models:
            if model.id == "piper":
                for v in model.voices:
                    item = QListWidgetItem(v.get("label", v["id"]))
                    item.setData(Qt.ItemDataRole.UserRole, v["id"])
                    # Mark already-downloaded voices
                    voice_path = self._models_root / "ml" / "piper" / f"{v['id']}.onnx"
                    if voice_path.exists():
                        item.setText(item.text() + "  ✓")
                        item.setForeground(Qt.GlobalColor.darkGreen)
                    self._voice_list.addItem(item)
        layout.addWidget(self._voice_list)

    # ── Download logic ────────────────────────────────────────────────────────

    def _on_download(self) -> None:
        self._download_btn.setEnabled(False)
        self._progress_bar.show()
        self._status_lbl.show()
        self._status_lbl.setText("Starting download…")
        self._progress_bar.setRange(0, 0)  # indeterminate until we get size

        if self._active_model_id == "kokoro":
            task = self._download_kokoro
        elif self._active_model_id == "piper":
            selected = [
                self._voice_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._voice_list.count())
                if self._voice_list.item(i).isSelected()
            ]
            if not selected:
                self._status_lbl.setText("Select at least one voice.")
                self._download_btn.setEnabled(True)
                self._progress_bar.hide()
                return
            def task(s=selected):
                self._download_piper_voices(s)
        else:
            return

        self._worker = _DownloadWorker(task)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _download_kokoro(self) -> None:
        from huggingface_hub import snapshot_download
        dest = self._models_root / "ml" / "kokoro"
        dest.mkdir(parents=True, exist_ok=True)
        _log.info("downloading Kokoro-82M to %s", dest)

        def _progress_cb(transferred: int, total: int) -> None:
            self._worker.progress.emit(transferred, total, f"Kokoro-82M  {transferred // 1_048_576} / {total // 1_048_576} MB")

        snapshot_download(
            repo_id=_KOKORO_HF_REPO,
            local_dir=str(dest),
            tqdm_class=None,
        )
        _log.info("Kokoro-82M download complete → %s", dest)

    def _download_piper_voices(self, voice_ids: list[str]) -> None:
        from huggingface_hub import hf_hub_download
        dest = self._models_root / "ml" / "piper"
        dest.mkdir(parents=True, exist_ok=True)

        total = len(voice_ids) * 2  # .onnx + .json per voice
        done = 0
        for vid in voice_ids:
            # Piper voice files on rhasspy/piper-voices use path: {lang}/{name}/{quality}/{file}
            # e.g. en/en_US/lessac/medium/en_US-lessac-medium.onnx
            parts = vid.split("-")
            if len(parts) >= 3:
                lang_full = parts[0]          # e.g. en_US
                name = "-".join(parts[1:-1])  # e.g. lessac
                quality = parts[-1]           # e.g. medium
                lang_short = lang_full.split("_")[0]  # e.g. en
                subpath = f"{lang_short}/{lang_full}/{name}/{quality}"
            else:
                subpath = vid

            for ext in (f"{vid}.onnx", f"{vid}.onnx.json"):
                _log.info("downloading piper voice file: %s", ext)
                self._worker.progress.emit(done, total, f"Downloading {ext}…")
                try:
                    hf_hub_download(
                        repo_id=_PIPER_HF_REPO,
                        filename=f"{subpath}/{ext}",
                        local_dir=str(dest),
                        local_dir_use_symlinks=False,
                    )
                    done += 1
                except Exception as exc:
                    _log.error("failed to download %s: %s", ext, exc)
                    raise

    def _on_progress(self, done: int, total: int, desc: str) -> None:
        self._status_lbl.setText(desc)
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(done)
        else:
            self._progress_bar.setRange(0, 0)  # keep indeterminate

    def _on_finished(self, success: bool, message: str) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100 if success else 0)
        self._status_lbl.setText(message)
        self._download_btn.setEnabled(not success)
        if success:
            self._download_btn.setText("Done")
            self._close_btn.setText("Close")
