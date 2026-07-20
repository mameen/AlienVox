"""AlienVox entry point — PySide6 tray-first app."""
from __future__ import annotations

import sys
import threading
import time

from PySide6.QtWidgets import QApplication

from .about import AboutDialog
from .config import get_voices, load_effective_config, save_user_override
from .engines.base import SpeakParams
from .engines.registry import available_stacks
from .hotkey import start_listener
from . import logger as _logger
from .main_window import MainWindow
from .telemetry import Telemetry
from .tray import AlienVoxTray
from .version import version as get_version

_log = _logger.get_logger("main")


def _load_engine(engine_id: str):
    """Return a live TtsEngine for the active stack, or None."""
    if sys.platform == "win32":
        if engine_id == "sapi5":
            try:
                from .engines.sapi_win import SapiEngine
                return SapiEngine()
            except Exception as exc:
                _log.error("SapiEngine init failed: %s", exc)
                return None
        if engine_id == "speech_platform":
            try:
                from .engines.sapi_win import SpeechPlatformEngine
                return SpeechPlatformEngine()
            except Exception as exc:
                _log.warn("SpeechPlatformEngine init failed (runtime not installed?): %s", exc)
                return None
    # ML engines — Stage 3, not yet implemented
    if engine_id == "ml":
        _log.warn("ML engine requested but not yet implemented — no engine loaded")
        return None
    return None


def _speak_startup(engine, voice_id: str) -> None:
    """Play a spoken startup announcement to confirm the audio pipeline is alive."""
    import time as _time
    _time.sleep(0.6)  # let the UI finish painting first
    try:
        from .engines.base import SpeakParams
        engine.speak(
            "AlienVox is ready. The dedicated audio engine is running.",
            voice_id,
            SpeakParams(),
        )
        _log.info("startup announcement spoken")
    except Exception as exc:
        _log.warn("startup announcement failed: %s", exc)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("AlienVox")
    app.setOrganizationName("AlienTech.Software")
    app.setQuitOnLastWindowClosed(False)

    tel = Telemetry()
    log_path = _logger.init(tel.session_id)

    # ── Startup banner (printed to stdout so `run.py app` shows it) ───────────
    version = get_version()
    print(f"")
    print(f"  AlienVox  v{version}")
    print(f"  Session : {tel.session_id}")
    print(f"  Log     : {log_path}")
    print(f"")

    _log.info("AlienVox v%s starting — session %s", version, tel.session_id)
    tel.emit("app.start")

    cfg = load_effective_config()
    stacks = available_stacks()

    active_stack = cfg.get("engine", "sapi5")
    active_model = cfg.get("model", "")
    _log.info("active stack=%s model=%s", active_stack, active_model or "(none)")
    engine = _load_engine(active_stack)
    if engine:
        _log.info("engine loaded: %s", type(engine).__name__)
    else:
        _log.warn("no engine loaded for stack=%s", active_stack)

    _main_window: MainWindow | None = None
    _about_dialog: AboutDialog | None = None
    _speak_lock = threading.Lock()

    def speak(text: str | None = None) -> None:
        """Speak text — from provided string or captured selection.

        Called from tray menu (no text → capture selection) or main window
        Play button (text provided → use editor content directly).
        """
        if not _speak_lock.acquire(blocking=False):
            _do_stop()
            return
        try:
            rid = tel.new_request_id()
            start_ms = time.time_ns() // 1_000_000
            tray.set_speaking()

            # Use provided text (from main window editor) or capture from selection
            if text is None:
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
                rate=cfg.get("rate", 0),
                pitch=cfg.get("pitch", 0),
                volume=cfg.get("volume", 100),
                hotkey=cfg.get("hotkey", ""),
                text_chars=len(text),
                text_bytes=len(text.encode()),
                version=get_version(),
            )

            if engine and text:
                params = SpeakParams(
                    rate=cfg.get("rate", 0),
                    pitch=cfg.get("pitch", 0),
                    volume=cfg.get("volume", 100),
                )
                engine.speak(text, cfg.get("voice", ""), params)

                # Emit first_audio telemetry (latency to SAPI submit) — matches Rust pattern
                tel.emit(
                    "tts.first_audio",
                    request_id=rid,
                    engine=active_stack,
                    model=active_model,
                    latency_ms=time.time_ns() // 1_000_000 - start_ms,
                    status="submitted_to_sapi",
                )

                # Wait for completion with finite timeout (Rust: SpeakCompleteEvent + WaitForSingleObject)
                completed = False
                try:
                    completed = engine.wait_until_done(30_000)  # 30s timeout, not -1
                except Exception as exc:
                    tel.emit("tts.error", request_id=rid, status="error",
                             detail=f"WaitUntilDone failed: {exc}")
                    tray.set_error(str(exc))

                if completed:
                    tel.emit("tts.playback_end", request_id=rid, engine=active_stack,
                             model=active_model, status="complete")
                else:
                    tel.emit("tts.error", request_id=rid, status="timeout",
                             detail="WaitUntilDone timed out after 30s")
                    tray.set_error("TTS playback timed out")

            tray.set_idle()
            tel.emit("speak.done", request_id=rid, engine=active_stack, status="ok")
        except Exception as exc:
            tel.emit("tts.error", status="error", detail=str(exc))
            tray.set_error(str(exc))
        finally:
            _speak_lock.release()

    def speak_async(text: str | None = None) -> None:
        """Async wrapper — spawns daemon thread with optional text argument."""
        threading.Thread(target=speak, args=(text,), daemon=True).start()

    # ── Persistence callbacks ───────────────────────────────────────────────

    def on_voice_changed(vid: str) -> None:
        save_user_override({"voice": vid})
        if engine and active_stack == "sapi5":
            voices = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
            tray.populate_voices(voices, vid, lambda v: on_voice_changed(v))
        elif engine and active_stack == "ml":
            # Refresh ML voices from engine (PiperEngine reads from stacks.yaml)
            ml_voices = engine.list_voices() if hasattr(engine, 'list_voices') else []
            if ml_voices:
                tray.populate_voices(
                    [{"id": v.id, "label": v.name} for v in ml_voices],
                    vid,
                    lambda v: on_voice_changed(v),
                )

    def on_config_saved(patch: dict[str, Any]) -> None:
        save_user_override(patch)

    def _do_stop() -> None:
        if engine:
            engine.stop()
        tray.set_idle()

    def _ensure_main_window() -> MainWindow:
        nonlocal _main_window
        if _main_window is None:
            # Eagerly enumerate voices so the dropdown is populated on first show
            win_live_voices: dict[str, list[dict]] = {}
            if engine:
                try:
                    vlist = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
                    win_live_voices[active_stack] = vlist
                    _log.info("window: loaded %d voices for stack=%s", len(vlist), active_stack)
                except Exception as exc:
                    _log.warn("window: voice enumeration failed: %s", exc)

            _main_window = MainWindow(
                stacks=stacks,
                telemetry=tel,
                on_speak=speak_async,
                on_stop=_do_stop,
                on_voice_changed=on_voice_changed,
                on_config_saved=on_config_saved,
                on_about=open_about,
                live_voices=win_live_voices,
                current_voice_id=cfg.get("voice", ""),
            )
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
    # For ML engines, populate from stacks.yaml if not already set
    elif active_stack == "ml" and not voices:
        try:
            voices = get_voices(active_stack, active_model or "piper")
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

    # Spoken startup announcement — confirms audio pipeline is alive.
    if engine and active_stack == "sapi5":
        voice_id = cfg.get("voice", "")
        if not voice_id:
            try:
                all_voices = engine.list_voices()
                voice_id = all_voices[0].id if all_voices else ""
            except Exception:
                voice_id = ""
        threading.Thread(
            target=_speak_startup,
            args=(engine, voice_id),
            daemon=True,
        ).start()

    hotkey_listener = start_listener(
        cfg.get("hotkey", "<ctrl>+<esc>"),
        speak_async,
    )

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
