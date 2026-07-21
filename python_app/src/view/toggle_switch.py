"""ToggleSwitch — a reusable iOS/Material-style toggle switch.

PySide6/QtWidgets has no built-in switch control (QtQuick Controls does,
via `Switch`, but this app uses QWidgets, not QML) — custom-painted
QAbstractButton subclass instead. Used anywhere the app needs an on/off
toggle (global Enhanced playback, per-voice enable/disable in the
Settings dialog, ...) so every toggle in the app looks and behaves the
same rather than each screen inventing its own checkbox/button variant.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QWidget

_TRACK_ON = QColor("#1a1a1a")
_TRACK_OFF = QColor("#d0d0d0")
_KNOB = QColor("#ffffff")


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_TRACK_ON if self.isChecked() else _TRACK_OFF)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob_d = rect.height() - 4
        x = rect.width() - knob_d - 2 if self.isChecked() else 2
        painter.setBrush(_KNOB)
        painter.drawEllipse(x, 2, knob_d, knob_d)
        painter.end()
