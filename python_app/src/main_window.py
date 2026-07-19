"""Main window — Balabolka-style testing and settings UI.

Mirrors the Rust/Tauri frontend design:
  Toolbar → Engine tabs → Voice controls bar → Audio sliders → Text editor → Status bar

Opened from the tray "Settings…" item (or double-click in the future).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QUrl, Signal, QSize
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap, QPolygon
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStatusBar,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import get_controls, get_voices, list_models, load_effective_config, save_user_override
from .engines.registry import StackInfo

_ACCENT = "#0078d4"
_TOOLBAR_BG = "#f5f5f5"
_TABS_BG = "#e8e8e8"
_VOICEBAR_BG = "#f5f5f5"
_SLIDER_BG = "#fafafa"


class _SliderRow(QWidget):
    """Label + horizontal slider + live value — horizontal layout for the slider strip."""

    valueChanged = Signal(float)

    def __init__(
        self,
        label: str,
        min_val: float,
        max_val: float,
        default: float,
        step: float = 1.0,
        fmt: str = "{:.0f}",
        enabled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self._step = step
        self._min = min_val
        self._max = max_val

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(label)
        self._name_lbl.setStyleSheet("font-size:11px; color:#666;")
        self._val_lbl = QLabel(fmt.format(default))
        self._val_lbl.setStyleSheet("font-size:11px; font-weight:600; color:#333;")
        top.addWidget(self._name_lbl)
        top.addStretch()
        top.addWidget(self._val_lbl)
        vbox.addLayout(top)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        # Qt sliders are integer-only; scale by 1000 for float precision
        scale = 1000
        self._scale = scale
        self._slider.setRange(int(min_val * scale), int(max_val * scale))
        self._slider.setValue(int(default * scale))
        self._slider.setSingleStep(max(1, int(step * scale)))
        self._slider.setEnabled(enabled)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: #d0d0d0;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {_ACCENT};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                height: 14px;
                margin: -4px 0;
                background: #ffffff;
                border: 2px solid {_ACCENT};
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:disabled {{
                border-color: #aaa;
            }}
        """)
        self._slider.valueChanged.connect(self._on_change)
        vbox.addWidget(self._slider)

    def _on_change(self, raw: int) -> None:
        v = raw / self._scale
        self._val_lbl.setText(self._fmt.format(v))
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self._slider.value() / self._scale

    def setValue(self, v: float) -> None:
        self._slider.setValue(int(v * self._scale))

    def setEnabled(self, enabled: bool) -> None:
        self._slider.setEnabled(enabled)
        self._name_lbl.setStyleSheet(
            f"font-size:11px; color:{'#666' if enabled else '#aaa'};"
        )


class MainWindow(QMainWindow):
    """Balabolka-style main window — testing harness and settings."""

    speak_requested = Signal(str, str, str, dict)   # text, engine, voice, params
    stop_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()

    def __init__(
        self,
        stacks: list[StackInfo],
        telemetry=None,
        on_speak: Callable | None = None,
        on_stop: Callable | None = None,
        sapi5_voices: list[dict] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("AlienVox")
        self.resize(720, 540)
        self.setMinimumSize(560, 400)
        # Qt.Window ensures it gets its own taskbar button even when parented
        self.setWindowFlags(Qt.WindowType.Window)

        self._stacks = stacks
        self._tel = telemetry
        self._on_speak_cb = on_speak
        self._on_stop_cb = on_stop
        self._pending_sapi5_voices = sapi5_voices

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voicesl()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voicesl()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voicesl()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voicesl()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voicesl()
        self._build_statusbar()
        self._load_stacks()

        # Populate SAPI5 voices if available (engine was loaded at startup)
        if sapi5_voices:
            self.update_sapi_voices(sapi5_voices)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setStyleSheet(f"""
            QToolBar {{
                background: {_TOOLBAR_BG};
                border-bottom: 1px solid #d0d0d0;
                spacing: 2px;
                padding: 2px 4px;
            }}
            QToolButton {{
                border: 1px solid transparent;
                background: transparent;
                padding: 3px 5px;
                font-size: 13px;
                min-width: 24px;
                min-height: 24px;
            }}
            QToolButton:hover {{
                border-color: #a0a0a0;
                background: #e8e8e8;
            }}
            QToolButton:disabled {{ color: #9a9a9a; }}
        """)

        def _text_btn(text: str, tip: str, slot=None) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            if slot:
                b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        def _icon_btn(icon: QIcon, tip: str, slot=None) -> QToolButton:
            b = QToolButton()
            b.setIcon(icon)
            b.setIconSize(QSize(16, 16))
            b.setToolTip(tip)
            if slot:
                b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        def _sep() -> None:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("color: #d0d0d0; margin: 3px 2px;")
            tb.addWidget(sep)

        _text_btn("📄", "New document",  self._on_new)
        _text_btn("📂", "Open text file")
        _text_btn("💾", "Save document")
        _sep()
        _text_btn("🎵", "Export to WAV")
        _sep()
        self._btn_play  = _icon_btn(_make_play_icon(),  "Play (speak text)", self._on_play)
        self._btn_pause = _icon_btn(_make_pause_icon(), "Pause",             self._on_pause)
        self._btn_stop  = _icon_btn(_make_stop_icon(),  "Stop",              self._on_stop)
        self.addToolBar(tb)

    # ── Central widget ────────────────────────────────────────────────────────

    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(f"""
            QTabBar::tab {{
                padding: 6px 14px;
                font-size: 12px;
                background: {_TABS_BG};
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                background: #ffffff;
                border-bottom: 2px solid {_ACCENT};
                font-weight: 500;
            }}
            QTabBar::tab:hover:!selected {{ background:#d8d8d8; }}
            QTabBar::tab:disabled {{ color:#aaa; }}
            QTabWidget::pane {{ border:none; border-top:1px solid #d0d0d0; }}
        """)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        vbox.addWidget(self._tabs)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        sb.setStyleSheet(
            "QStatusBar { background:#f0f0f0; border-top:1px solid #d0d0d0; "
            "font-size:11px; color:#666; }"
        )
        self._status_lbl = QLabel("Ready")
        self._chars_lbl  = QLabel("0 chars")
        sb.addWidget(self._status_lbl)
        sb.addPermanentWidget(self._chars_lbl)
        self.setStatusBar(sb)

    # ── Stack tabs ────────────────────────────────────────────────────────────

    def _load_stacks(self) -> None:
        # SAPI 4 — always disabled (legacy)
        dummy = QWidget()
        self._tabs.addTab(dummy, "SAPI 4")
        self._tabs.setTabEnabled(0, False)

        for stack in self._stacks:
            tab = self._build_stack_tab(stack)
            self._tabs.addTab(tab, stack.name)
            if not stack.available:
                idx = self._tabs.count() - 1
                self._tabs.setTabEnabled(idx, False)

        # Select first available tab
        for i in range(self._tabs.count()):
            if self._tabs.isTabEnabled(i):
                self._tabs.setCurrentIndex(i)
                break

    def _build_stack_tab(self, stack: StackInfo) -> QWidget:
        w = QWidget()
        w.setProperty("stack_id", stack.id)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        if not stack.available:
            unavail = QLabel(f"<i>{stack.name} — {stack.platform_reason or 'not available on this platform'}</i>")
            unavail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(unavail, stretch=1)
            return w

        # Voice controls bar
        vbox.addWidget(self._build_voice_bar(stack))
        vbox.addWidget(self._hsep())

        # Audio sliders
        vbox.addWidget(self._build_slider_strip(stack))
        vbox.addWidget(self._hsep())

        # Text editor
        editor = QPlainTextEdit()
        editor.setPlaceholderText("Enter or paste text here…")
        editor.setFont(QFont("Consolas", 11))
        editor.setStyleSheet(
            "QPlainTextEdit { border:none; padding:8px; background:#ffffff; }"
        )
        editor.textChanged.connect(
            lambda: self._chars_lbl.setText(f"{len(editor.toPlainText())} chars")
        )
        w.setProperty("editor", editor)
        vbox.addWidget(editor, stretch=1)

        return w

    def _build_voice_bar(self, stack: StackInfo) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{_VOICEBAR_BG}; border-bottom:1px solid #d0d0d0;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        has_models = bool(stack.models)

        if has_models:
            model_combo = QComboBox()
            model_combo.setFixedWidth(220)
            model_combo.setStyleSheet(_combo_style())
            for m in stack.models:
                model_combo.addItem(m.name, m.id)
            bar.setProperty("model_combo", model_combo)
            layout.addWidget(model_combo)

        voice_combo = QComboBox()
        voice_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        voice_combo.setStyleSheet(_combo_style())
        bar.setProperty("voice_combo", voice_combo)

        # Populate initial voices
        if has_models and stack.models:
            first_model = stack.models[0]
            for v in first_model.voices:
                voice_combo.addItem(v.get("label", v["id"]), v["id"])
        elif stack.id == "sapi5":
            voice_combo.addItem("(populated from OS at runtime)", "")
        else:
            voices = get_voices(stack.id)
            for v in voices:
                voice_combo.addItem(v.get("label", v["id"]), v["id"])

        layout.addWidget(voice_combo)

        if has_models:
            # TTL spinbox
            from PySide6.QtWidgets import QSpinBox
            ttl_lbl = QLabel("TTL")
            ttl_lbl.setStyleSheet("font-size:11px; color:#555;")
            ttl_spin = QSpinBox()
            ttl_spin.setRange(0, 300)
            ttl_spin.setValue(30)
            ttl_spin.setSuffix(" s")
            ttl_spin.setFixedWidth(72)
            ttl_spin.setStyleSheet(_combo_style())
            layout.addWidget(ttl_lbl)
            layout.addWidget(ttl_spin)

        self._status_engine_lbl = QLabel("Ready")
        self._status_engine_lbl.setStyleSheet("font-size:11px; color:#555; min-width:100px;")
        layout.addWidget(self._status_engine_lbl)

        install_btn = QPushButton("Install" if not has_models else "Install Model")
        install_btn.setStyleSheet(_btn_style())
        install_btn.setFixedHeight(28)
        layout.addWidget(install_btn)

        if has_models:
            model_combo.currentIndexChanged.connect(
                lambda idx, s=stack, vc=voice_combo, mc=model_combo:
                    self._on_model_changed(s, mc.itemData(idx), vc)
            )

        return bar

    def _build_slider_strip(self, stack: StackInfo) -> QWidget:
        strip = QWidget()
        strip.setStyleSheet(f"background:{_SLIDER_BG};")
        grid = QHBoxLayout(strip)
        grid.setContentsMargins(8, 10, 8, 10)
        grid.setSpacing(20)

        cfg = load_effective_config(stack.id, user_file=None)
        controls = get_controls(stack.id)

        rate_spec   = controls.get("rate",   {})
        pitch_spec  = controls.get("pitch",  {})
        vol_spec    = controls.get("volume", {})

        s_rate = _SliderRow(
            "Rate", float(rate_spec.get("min", -10)), float(rate_spec.get("max", 10)),
            float(cfg.get("rate", rate_spec.get("default", 0))),
            enabled=rate_spec.get("applies", True),
        )
        s_pitch = _SliderRow(
            "Pitch", float(pitch_spec.get("min", -10)), float(pitch_spec.get("max", 10)),
            float(cfg.get("pitch", pitch_spec.get("default", 0))),
            enabled=pitch_spec.get("applies", True),
        )
        if not pitch_spec.get("applies", True):
            s_pitch._name_lbl.setText("Pitch (N/A)")

        s_vol = _SliderRow(
            "Volume", float(vol_spec.get("min", 0)), float(vol_spec.get("max", 100)),
            float(cfg.get("volume", vol_spec.get("default", 100))),
            enabled=vol_spec.get("applies", True),
        )

        for s in (s_rate, s_pitch, s_vol):
            grid.addWidget(s)

        strip.setProperty("slider_rate",   s_rate)
        strip.setProperty("slider_pitch",  s_pitch)
        strip.setProperty("slider_volume", s_vol)

        return strip

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_new(self) -> None:
        editor = self._active_editor()
        if editor:
            editor.clear()
        self._set_status("Ready")

    def _on_play(self) -> None:
        editor = self._active_editor()
        text = editor.toPlainText().strip() if editor else ""
        if not text:
            self._set_status("No text to speak")
            return
        self._set_status("Speaking…")
        if self._on_speak_cb:
            self._on_speak_cb(text)

    def _on_pause(self) -> None:
        if self._on_stop_cb:
            pass  # pause/resume via engine — wired later
        self._set_status("Paused")

    def _on_stop(self) -> None:
        if self._on_stop_cb:
            self._on_stop_cb()
        self._set_status("Stopped")

    def _on_tab_changed(self, idx: int) -> None:
        tab = self._tabs.widget(idx)
        if tab:
            stack_id = tab.property("stack_id") or ""
            self._set_status(f"Engine: {stack_id or '—'}")

    def _on_model_changed(self, stack: StackInfo, model_id: str, voice_combo: QComboBox) -> None:
        model = next((m for m in stack.models if m.id == model_id), None)
        voice_combo.clear()
        if model:
            for v in model.voices:
                voice_combo.addItem(v.get("label", v["id"]), v["id"])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _active_editor(self) -> QPlainTextEdit | None:
        tab = self._tabs.currentWidget()
        return tab.property("editor") if tab else None

    def _set_status(self, msg: str) -> None:
        self._status_lbl.setText(msg)
        if hasattr(self, "_status_engine_lbl"):
            self._status_engine_lbl.setText(msg)

    def set_speaking(self) -> None:
        self._set_status("Speaking…")

    def set_idle(self) -> None:
        self._set_status("Ready")

    def set_error(self, message: str) -> None:
        self._set_status(f"Error: {message}")

    def update_sapi_voices(self, voices: list[dict]) -> None:
        """Call after SAPI engine is live to fill the voice dropdown."""
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if tab and tab.property("stack_id") == "sapi5":
                # Find the voice bar widget (it has property "voice_combo" set in _build_voice_bar)
                voice_bar = None
                for child in tab.findChildren(QWidget):
                    if child.property("voice_combo"):
                        voice_bar = child
                        break
                if not voice_bar:
                    continue
                vc = voice_bar.property("voice_combo")
                if vc:
                    vc.clear()
                    for v in voices:
                        vc.addItem(v.get("label", v["id"]), v["id"])
                break

    @staticmethod
    def _hsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:#d0d0d0;")
        return f


# ── Toolbar icon painters ─────────────────────────────────────────────────────
# Painted icons so Qt doesn't render emoji glyphs (which ignore CSS color).
# Sizes and colours match the Rust/Tauri CSS:
#   play  → #22c55e (green)   pause → #6b7280 (gray)   stop → #ef4444 (red)

def _make_icon(size: int = 16) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    return pix


def _make_play_icon(size: int = 16) -> QIcon:
    pix = _make_icon(size)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#22c55e"))
    p.setPen(Qt.PenStyle.NoPen)
    m = size // 5
    tri = QPolygon([
        QPoint(m, m),
        QPoint(size - m, size // 2),
        QPoint(m, size - m),
    ])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pix)


def _make_pause_icon(size: int = 16) -> QIcon:
    pix = _make_icon(size)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#6b7280"))
    p.setPen(Qt.PenStyle.NoPen)
    bar_w = max(3, size // 4)
    gap   = max(2, size // 5)
    x1 = (size - bar_w * 2 - gap) // 2
    x2 = x1 + bar_w + gap
    my = size // 5
    p.drawRect(x1, my, bar_w, size - my * 2)
    p.drawRect(x2, my, bar_w, size - my * 2)
    p.end()
    return QIcon(pix)


def _make_stop_icon(size: int = 16) -> QIcon:
    pix = _make_icon(size)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#ef4444"))
    p.setPen(Qt.PenStyle.NoPen)
    m = size // 4
    p.drawRect(m, m, size - m * 2, size - m * 2)
    p.end()
    return QIcon(pix)


# ── Style helpers ─────────────────────────────────────────────────────────────

def _combo_style() -> str:
    return (
        "QComboBox { border:1px solid #c0c0c0; background:#ffffff; "
        "padding:4px 8px; font-size:12px; height:28px; }"
        "QComboBox::drop-down { border:none; }"
        "QComboBox QAbstractItemView { border:1px solid #c0c0c0; font-size:12px; }"
    )


def _btn_style() -> str:
    return (
        "QPushButton { border:1px solid #c0c0c0; background:#ffffff; "
        "padding:4px 14px; font-size:12px; }"
        "QPushButton:hover { background:#e8e8e8; }"
    )
