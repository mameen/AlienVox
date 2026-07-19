"""System tray icon and context menu (PySide6 QSystemTrayIcon)."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class AlienVoxTray:
    def __init__(
        self,
        app: QApplication,
        on_speak: Callable[[], None],
        on_stop: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._tray = QSystemTrayIcon(app)
        self._tray.setIcon(QIcon.fromTheme("audio-speakers"))  # placeholder

        menu = QMenu()
        menu.addAction("Speak Selection", on_speak)
        menu.addAction("Stop", on_stop)
        menu.addSeparator()
        menu.addAction("Settings…", on_settings)
        menu.addAction("About", lambda: self._tray.showMessage("AlienVox", "AlienVox TTS"))
        menu.addSeparator()
        menu.addAction("Quit", on_quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._tray.contextMenu().actions()[0].trigger()  # Speak Selection on left-click

    def show(self) -> None:
        self._tray.show()

    def set_icon_speaking(self) -> None:
        self._tray.setToolTip("AlienVox — speaking")

    def set_icon_idle(self) -> None:
        self._tray.setToolTip("AlienVox — idle")
