"""AlienVox entry point — PySide6 tray-first app."""
from __future__ import annotations

import sys
import threading

from PySide6.QtWidgets import QApplication

from .about import AboutDialog
from .config import load_effective_config, save_user_override
from .engines.registry import available_stacks
from .hotkey import start_listener
from .preferences import PreferencesWindow
from .telemetry import Telemetry
from .tray import AlienVoxTray


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AlienVox")
    app.setOrganizationName("AlienTech.Software")
    app.setQuitOnLastWindowClosed(False)

    tel = Telemetry()
    tel.emit("app.start")

    cfg = load_effective_config()
    stacks = available_stacks()

    _prefs_window: PreferencesWindow | None = None
    _about_dialog: AboutDialog | None = None
    _speaking = threading.Lock()

    def speak() -> None:
        if not _speaking.acquire(blocking=False):
            # already speaking — treat as stop
            _do_stop()
            return
        try:
            rid = tel.new_request_id()
            tray.set_speaking()

            # Stage 1: capture only — audio wired in Stage 3
            try:
                from .capture import get_selected_text
                text = get_selected_text()
            except ImportError:
                text = ""

            tel.emit(
                "speak.triggered",
                request_id=rid,
                engine=cfg.get("engine", "sapi5"),
                model=cfg.get("model", ""),
                voice=cfg.get("voice", ""),
                text_chars=len(text),
                text_bytes=len(text.encode()),
            )

            # TODO (Stage 3): call engine.speak(text, ...)
            tray.set_idle()
        except Exception as exc:
            tel.emit("tts.error", status="error", detail=str(exc))
            tray.set_error(str(exc))
        finally:
            _speaking.release()

    def speak_async() -> None:
        threading.Thread(target=speak, daemon=True).start()

    def _do_stop() -> None:
        # TODO (Stage 3): call engine.stop()
        tray.set_idle()
        if _speaking.locked():
            _speaking.release()

    def open_settings() -> None:
        nonlocal _prefs_window
        if _prefs_window is None or not _prefs_window.isVisible():
            _prefs_window = PreferencesWindow(stacks=stacks, telemetry=tel)
        _prefs_window.show()
        _prefs_window.raise_()
        _prefs_window.activateWindow()

    def open_about() -> None:
        nonlocal _about_dialog
        if _about_dialog is None:
            _about_dialog = AboutDialog()
        _about_dialog.exec()

    def quit_app() -> None:
        tel.emit("app.quit")
        hotkey_listener.stop()
        app.quit()

    tray = AlienVoxTray(
        on_speak=speak_async,
        on_stop=_do_stop,
        on_settings=open_settings,
        on_about=open_about,
        on_quit=quit_app,
    )

    # Populate Voice submenu from config
    active_stack = cfg.get("engine", "sapi5")
    active_model = cfg.get("model", "")
    from .config import get_voices
    voices = get_voices(active_stack, active_model) if active_model else []
    tray.populate_voices(
        voices,
        current_voice_id=cfg.get("voice", ""),
        on_select=lambda vid: (
            save_user_override({"voice": vid}),
            tel.emit("config.changed", engine=active_stack, detail="voice"),
        ),
    )

    tray.show()

    hotkey_listener = start_listener(
        cfg.get("hotkey", "<ctrl>+<esc>"),
        speak_async,
    )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
