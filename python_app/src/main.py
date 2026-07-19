"""AlienVox entry point — PySide6 tray-first app."""
from __future__ import annotations

import sys
import threading

from PySide6.QtWidgets import QApplication

from .capture import get_selected_text
from .config import load_effective_config, save_user_override
from .engines.sapi_win import SapiEngine
from .engines.base import SpeakParams
from .hotkey import start_listener
from .tray import AlienVoxTray


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_effective_config()
    engine = SapiEngine()
    _speaking = threading.Lock()

    def speak() -> None:
        if not _speaking.acquire(blocking=False):
            engine.stop()
            return
        try:
            text = get_selected_text()
            if not text:
                return
            voices = engine.list_voices()
            voice_id = cfg.get("voice") or (voices[0].id if voices else "0")
            params = SpeakParams(
                rate=cfg.get("rate", 0),
                pitch=cfg.get("pitch", 0),
                volume=cfg.get("volume", 100),
            )
            tray.set_icon_speaking()
            engine.speak(text, voice_id, params)
        finally:
            tray.set_icon_idle()
            _speaking.release()

    def speak_async() -> None:
        threading.Thread(target=speak, daemon=True).start()

    def stop() -> None:
        engine.stop()

    def open_settings() -> None:
        pass  # TODO: open Preferences window

    def quit_app() -> None:
        engine.stop()
        hotkey_listener.stop()
        app.quit()

    tray = AlienVoxTray(
        app,
        on_speak=speak_async,
        on_stop=stop,
        on_settings=open_settings,
        on_quit=quit_app,
    )
    tray.show()

    hotkey_listener = start_listener(cfg.get("hotkey", "<ctrl>+<esc>"), speak_async)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
