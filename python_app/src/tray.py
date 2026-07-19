"""System tray icon and context menu."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_ICONS_DIR = Path(__file__).parent / "resources" / "icons"


def _icon(name: str) -> QIcon:
    path = _ICONS_DIR / name
    return QIcon(str(path)) if path.exists() else QIcon()


class AlienVoxTray:
    def __init__(
        self,
        on_speak: Callable[[], None],
        on_stop: Callable[[], None],
        on_settings: Callable[[], None],
        on_about: Callable[[], None],
        on_quit: Callable[[], None],
        on_window_toggle: Callable[[], None] | None = None,
    ) -> None:
        self._tray = QSystemTrayIcon()
        self._icons = {
            "idle":     _icon("idle.png"),
            "speaking": _icon("speaking.png"),
            "error":    _icon("error.png"),
        }
        self._tray.setIcon(self._icons["idle"])
        self._tray.setToolTip("AlienVox — idle")

        self._on_speak = on_speak
        self._on_stop = on_stop
        self._on_window_toggle = on_window_toggle or on_settings

        menu = QMenu()
        self._act_speak = menu.addAction("Speak Selection")
        self._act_stop  = menu.addAction("Stop")
        self._act_stop.setEnabled(False)
        menu.addSeparator()
        self._voice_menu = menu.addMenu("Voice ▸")
        menu.addSeparator()
        menu.addAction("Settings…", on_settings)
        menu.addAction("About",     on_about)
        menu.addSeparator()
        menu.addAction("Quit",      on_quit)

        self._act_speak.triggered.connect(on_speak)
        self._act_stop.triggered.connect(on_stop)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    # ── State transitions ────────────────────────────────────────────────────

    def set_speaking(self) -> None:
        self._tray.setIcon(self._icons["speaking"])
        self._tray.setToolTip("AlienVox — speaking")
        self._act_speak.setEnabled(False)
        self._act_stop.setEnabled(True)

    def set_idle(self) -> None:
        self._tray.setIcon(self._icons["idle"])
        self._tray.setToolTip("AlienVox — idle")
        self._act_speak.setEnabled(True)
        self._act_stop.setEnabled(False)

    def set_error(self, message: str = "") -> None:
        self._tray.setIcon(self._icons["error"])
        tip = f"AlienVox — error: {message}" if message else "AlienVox — error"
        self._tray.setToolTip(tip[:127])  # Windows tooltip length limit

    # ── Voice submenu (data-driven) ──────────────────────────────────────────

    def populate_voices(
        self,
        voices: list[dict[str, str]],
        current_voice_id: str,
        on_select: Callable[[str], None],
    ) -> None:
        """Rebuild Voice ▸ submenu from a list of {id, label} dicts."""
        self._voice_menu.clear()
        if not voices:
            self._voice_menu.addAction("(no voices installed)").setEnabled(False)
            return
        for v in voices:
            act = self._voice_menu.addAction(v.get("label", v["id"]))
            act.setCheckable(True)
            act.setChecked(v["id"] == current_voice_id)
            vid = v["id"]
            act.triggered.connect(lambda checked, _id=vid: on_select(_id))

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click → speak selection (primary action)
            self._on_speak()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Double click → toggle main window
            self._on_window_toggle()
