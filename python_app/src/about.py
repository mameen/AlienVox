"""About dialog — matches the Rust/Tauri about.html design."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

_ICONS = Path(__file__).parent / "resources" / "icons"


from .version import version as get_version


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About AlienVox")
        self.setFixedSize(580, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_separator())
        root.addWidget(self._build_scroll(), stretch=1)
        root.addWidget(self._build_separator())
        root.addWidget(self._build_footer())
        root.addWidget(self._build_close_row())

    # ── Sections ──────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#ffffff;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)

        # Logo
        logo = QLabel()
        logo.setFixedSize(72, 72)
        logo.setStyleSheet("border-radius:8px; background:#f5f5f5; padding:4px;")
        pix_path = _ICONS / "icon_256x256.png"
        if pix_path.exists():
            pix = QPixmap(str(pix_path)).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # Meta text
        meta = QVBoxLayout()
        meta.setSpacing(3)

        name_lbl = QLabel("AlienVox")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        name_lbl.setFont(f)
        name_lbl.setStyleSheet("color:#1a1a1a;")

        ver_lbl = QLabel(f"v{get_version()} — Python / PySide6")
        ver_lbl.setStyleSheet("color:#666; font-size:11px;")

        tag_lbl = QLabel(
            'Lightweight tray-first "Speak Selection" utility for Windows & macOS.'
        )
        tag_lbl.setStyleSheet("color:#0078d4; font-size:12px;")
        tag_lbl.setWordWrap(True)

        meta.addWidget(name_lbl)
        meta.addWidget(ver_lbl)
        meta.addWidget(tag_lbl)
        meta.addStretch()

        layout.addLayout(meta, stretch=1)
        return w

    def _build_scroll(self) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setStyleSheet("background:#fafafa;")
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background:#fafafa;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(24, 16, 24, 20)
        vbox.setSpacing(0)

        sections = [
            (
                "What is AlienVox?",
                None,
                [
                    "AlienVox fills a gap that has existed for decades: Windows still lacks a simple, "
                    "universal Speak Selection feature like macOS's Option + Esc. Highlight any text "
                    "and hear it spoken instantly — no extra paragraphs, no UI wrappers, no heavy screen readers.",
                    "This is the Python + PySide6 implementation: a lightweight, tray-first desktop app "
                    "with local TTS engines and a clean path to neural voices.",
                ],
            ),
            (
                "Tech Stack",
                None,
                [
                    ("Language", "Python 3.11+"),
                    ("UI Framework", "PySide6 — Qt6 for Windows and macOS"),
                    ("System Tray", "QSystemTrayIcon — platform-native integration"),
                    ("TTS — OS", "Windows SAPI 5 via pywin32 COM"),
                    ("TTS — ML", "Kokoro-82M, Piper, Dia, VibeVoice (in-process ONNX)"),
                    ("Config", "stacks.yaml bundled next to executable"),
                ],
            ),
            (
                "TTS Engines & Models",
                None,
                [
                    ("Kokoro-82M", "Primary local neural TTS. Open weights, Apache 2.0, ~82 M parameters."),
                    ("Native OS TTS", "Windows SAPI 5 — always available as the reliability floor."),
                    ("Piper", "Small offline neural TTS (MIT). Stable fallback."),
                    ("VibeVoice-Realtime-0.5B", "Streaming local TTS experiment (MIT, research stage)."),
                    ("Dia", "Expressive dialogue generation (Apache 2.0, GPU-oriented)."),
                ],
            ),
            (
                "Design Philosophy",
                None,
                [
                    ("Frictionless execution", "Zero config for the primary path — global hotkey → speak selection."),
                    ("Strict respect for selection", "Only the highlighted text is spoken, nothing more."),
                    ("Hybrid audio pipeline", "Local zero-latency APIs first; clean path to neural voices."),
                    ("Unobtrusive presence", "Lives in the system tray — no active window during operation."),
                    ("Privacy-first", "Captured text is never logged, cached, or persisted locally."),
                ],
            ),
            (
                "License",
                "This project is open-source. See the LICENSE file in the repository root for details.",
                [],
            ),
        ]

        for title, prose, items in sections:
            vbox.addWidget(self._section(title, prose, items))

        vbox.addStretch()
        area.setWidget(content)
        return area

    def _section(self, title: str, prose: str | None, items: list) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(6)

        # Title
        hdr = QLabel(title)
        hf = QFont()
        hf.setPointSize(10)
        hf.setBold(True)
        hdr.setFont(hf)
        hdr.setStyleSheet("color:#1a1a1a; border-bottom:1px solid #e8e8e8; padding-bottom:3px;")
        layout.addWidget(hdr)

        if prose:
            if isinstance(prose, list):
                for p in prose:
                    lbl = QLabel(p)
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet("color:#333; font-size:12px; line-height:1.5;")
                    layout.addWidget(lbl)
            else:
                lbl = QLabel(prose)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("color:#333; font-size:12px;")
                layout.addWidget(lbl)

        for item in items:
            if isinstance(item, str):
                lbl = QLabel(item)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("color:#333; font-size:12px;")
                layout.addWidget(lbl)
            else:
                key, val = item
                row = QHBoxLayout()
                row.setContentsMargins(18, 0, 0, 0)
                bullet = QLabel("●")
                bullet.setFixedWidth(14)
                bullet.setStyleSheet("color:#0078d4; font-size:8px;")
                bullet.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                kl = QLabel(f"<b>{key}:</b> {val}")
                kl.setWordWrap(True)
                kl.setStyleSheet("color:#333; font-size:12px;")
                kl.setTextFormat(Qt.TextFormat.RichText)
                row.addWidget(bullet)
                row.addWidget(kl, stretch=1)
                layout.addLayout(row)

        return w

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fafafa; border-top:1px solid #e8e8e8;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(24, 8, 24, 8)

        copy_lbl = QLabel("© 2026 AlienTech.Software")
        copy_lbl.setStyleSheet("color:#888; font-size:10px;")

        gh_btn = QPushButton("GitHub ↗")
        gh_btn.setFlat(True)
        gh_btn.setStyleSheet(
            "color:#0078d4; font-size:10px; border:none; background:transparent;"
            "text-decoration:underline; padding:0;"
        )
        gh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gh_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/alientech-software/alienvox")
            )
        )

        layout.addWidget(copy_lbl)
        layout.addStretch()
        layout.addWidget(gh_btn)
        return w

    def closeEvent(self, event):
        """Override native Windows [X] close to ensure proper cleanup."""
        self.accept()
        event.accept()

    def _build_close_row(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#ffffff;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(24, 10, 24, 14)
        layout.addStretch()
        btn = QPushButton("Close")
        btn.setFixedWidth(80)
        btn.setStyleSheet(
            "border:1px solid #c0c0c0; background:#ffffff; padding:5px 0;"
            "font-size:12px;"
            "QPushButton:hover { background:#e8e8e8; }"
        )
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        return w

    def _build_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#e8e8e8;")
        return line
