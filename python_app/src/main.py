"""AlienVox entry point — PySide6 tray-first app."""
from __future__ import annotations

import sys
import threading

from PySide6.QtWidgets import QApplication

from .about import AboutDialog
from .config import get_voices, load_effective_config, save_user_override
from .engines.base import SpeakParams
from .engines.registry import available_stacks
from .hotkey import start_listener
from .main_window import MainWindow
from .telemetry import Telemetry
from .tray import AlienVoxTray


def _load_engine(engine_id: str):
    """Return a live TtsEngine for the active stack, or None."""
    if engine_id == "sapi5" and sys.platform == "win32":
        try:
            from .engines.sapi_win import SapiEngine
            return SapiEngine()
        except Exception:
            return None
    # ML engines wired in Stage 3
    return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AlienVox")
    app.setOrganizationName("AlienTech.Software")
    app.setQuitOnLastWindowClosed(False)

    tel = Telemetry()
    tel.emit("app.start")

    cfg = load_effective_config()
    stacks = available_stacks()

    active_stack = cfg.get("engine", "sapi5")
    active_model = cfg.get("model", "")
    engine = _load_engine(active_stack)

    _main_window: MainWindow | None = None
    _about_dialog: AboutDialog | None = None
    _speak_lock = threading.Lock()

    def speak() -> None:
        if not _speak_lock.acquire(blocking=False):
            _do_stop()
            return
        try:
            rid = tel.new_request_id()
            tray.set_speaking()

            text = ""
            try:
                from .capture import get_selected_text
                text = get_selected_text()
            except ImportError:
                pass

            tel.emit(
                "speak.triggered",
                request_id=rid,
                engine=active_stack,
                model=active_model,
                voice=cfg.get("voice", ""),
                text_chars=len(text),
                text_bytes=len(text.encode()),
            )

            if engine and text:
                params = SpeakParams(
                    rate=cfg.get("rate", 0),
                    pitch=cfg.get("pitch", 0),
                    volume=cfg.get("volume", 100),
                )
                engine.speak(text, cfg.get("voice", ""), params)
                # speak() is async on SAPI — wait for completion
                # SpVoice.WaitUntilDone(-1) blocks until queue is empty
                try:
                    engine._sapi.WaitUntilDone(-1)
                except Exception:
                    pass

            tray.set_idle()
            tel.emit("speak.done", request_id=rid, engine=active_stack, status="ok")
        except Exception as exc:
            tel.emit("tts.error", status="error", detail=str(exc))
            tray.set_error(str(exc))
        finally:
            _speak_lock.release()

    def speak_async() -> None:
        threading.Thread(target=speak, daemon=True).start()

    def _do_stop() -> None:
        if engine:
            engine.stop()
        tray.set_idle()

    def _ensure_main_window() -> MainWindow:
        nonlocal _main_window
        if _main_window is None:
            _main_window = MainWindow(
                stacks=stacks,
                telemetry=tel,
                on_speak=speak_async,
                on_stop=_do_stop,
            )
            if engine and active_stack == "sapi5":
                try:
                    live = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
                    _main_window.update_sapi_voices(live)
                except Exception:
                    pass
        return _main_window

    def open_settings() -> None:
        w = _ensure_main_window()
        w.show()
        w.raise_()
        w.activateWindow()

    def toggle_window() -> None:
        w = _ensure_main_window()
        if w.isVisible():
            w.hide()
        else:
            w.show()
            w.raise_()
            w.activateWindow()

    def open_about() -> None:
        nonlocal _about_dialog
        if _about_dialog is None:
            _about_dialog = AboutDialog()
        _about_dialog.exec()

    def quit_app() -> None:
        tel.emit("app.quit")
        hotkey_listener.stop()
        if engine:
            engine.stop()
        app.quit()

    voices = get_voices(active_stack, active_model) if active_model else []
    # For sapi5, populate from live engine at runtime
    if active_stack == "sapi5" and engine:
        try:
            live_voices = engine.list_voices()
            voices = [{"id": v.id, "label": v.name} for v in live_voices]
        except Exception:
            pass

    tray = AlienVoxTray(
        on_speak=speak_async,
        on_stop=_do_stop,
        on_settings=open_settings,
        on_about=open_about,
        on_quit=quit_app,
        on_window_toggle=toggle_window,
    )

    tray.populate_voices(
        voices,
        current_voice_id=cfg.get("voice", ""),
        on_select=lambda vid: (
            save_user_override({"voice": vid}),
            tel.emit("config.changed", engine=active_stack, detail="voice"),
        ),
    )

    tray.show()
    open_settings()  # show main window on startup

    hotkey_listener = start_listener(
        cfg.get("hotkey", "<ctrl>+<esc>"),
        speak_async,
    )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
