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
        on_save_settings: Callable[[], None] | None = None,
        on_load_settings: Callable[[], None] | None = None,
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
        if on_save_settings:
            menu.addAction("Save Settings…", on_save_settings)
        if on_load_settings:
            menu.addAction("Load Settings…", on_load_settings)
        menu.addAction("About",     on_about)
        menu.addSeparator()
        menu.addAction("Quit",      on_quit)

        # Use lambda to discard the 'checked' bool that triggered() always passes.
        # Without this, speak(True) reaches len(True) and crashes.
        self._act_speak.triggered.connect(lambda _: on_speak())
        self._act_stop.triggered.connect(lambda _: on_stop())
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

    # ── Voice submenu (data-driven, two-level) ───────────────────────────────

    def populate_voice_menu(
        self,
        groups: list[dict],
        current_voice_id: str,
        on_select: Callable[[str, str, str], None],
    ) -> None:
        """Rebuild the two-level Voice ▸ submenu.

        groups is a list of stack descriptors:
          {"id": "sapi5",  "label": "SAPI5",   "voices": [{id, label}, ...]}
          {"id": "ml",     "label": "ML / AI",  "models": [
              {"id": "kokoro", "label": "Kokoro", "voices": [{id, label}, ...]}
          ]}

        on_select(stack_id, model_id, voice_id) is called when the user picks a voice.
        """
        self._voice_menu.clear()
        has_any = False

        for grp in groups:
            stack_id = grp["id"]
            stack_label = grp.get("label", stack_id)

            if "models" in grp:
                # ML-style: Stack ▸ Models ▸ [model] ▸ Voice (4 levels)
                has_any = True
                models_menu = self._voice_menu.addMenu(f"{stack_label} · Models")
                for model in grp["models"]:
                    voices = model.get("voices", [])
                    if not voices:
                        continue
                    model_submenu = models_menu.addMenu(model.get("label", model["id"]))
                    for v in voices:
                        act = model_submenu.addAction(v.get("label", v["id"]))
                        act.setCheckable(True)
                        act.setChecked(v["id"] == current_voice_id)
                        _sid = stack_id
                        _mid = model["id"]
                        _vid = v["id"]
                        act.triggered.connect(
                            lambda _, _sid=_sid, _mid=_mid, _vid=_vid: on_select(_sid, _mid, _vid)
                        )
            else:
                # SAPI-style: Stack ▸ Voice
                voices = grp.get("voices", [])
                if not voices:
                    continue
                has_any = True
                stack_menu = self._voice_menu.addMenu(stack_label)
                for v in voices:
                    act = stack_menu.addAction(v.get("label", v["id"]))
                    act.setCheckable(True)
                    act.setChecked(v["id"] == current_voice_id)
                    _sid = stack_id
                    _vid = v["id"]
                    act.triggered.connect(
                        lambda _, _sid=_sid, _vid=_vid: on_select(_sid, "", _vid)
                    )

        if not has_any:
            self._voice_menu.addAction("(no voices installed)").setEnabled(False)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click → speak selection (primary action)
            self._on_speak()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Double click → toggle main window
            self._on_window_toggle()
