"""AlienVox entry point — PySide6 tray-first app."""
from __future__ import annotations

import sys
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engines.base import TtsEngine

from PySide6.QtWidgets import QApplication

from . import logger as _logger
from .about import AboutDialog
from .config import get_voices, load_effective_config, save_user_override
from .config import models_root as _models_root
from .engines.base import SpeakParams
from .engines.registry import available_stacks
from .hotkey import start_listener
from .main_window import MainWindow
from .telemetry import Telemetry
from .tray import AlienVoxTray
from .version import version as get_version

_log = _logger.get_logger("main")


def _load_engine(engine_id: str, model_id: str = "") -> "TtsEngine | None":
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
    if engine_id == "ml":
        model = model_id or "kokoro"
        if model == "kokoro":
            try:
                from .engines.kokoro_engine import KokoroEngine
                eng = KokoroEngine()
                _log.info("KokoroEngine loaded")
                return eng
            except Exception as exc:
                _log.error("KokoroEngine init failed: %s", exc)
                return None
        _log.warn("ML model=%s not yet implemented", model)
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
    print("")
    print(f"  AlienVox  v{version}")
    print(f"  Session : {tel.session_id}")
    print(f"  Log     : {log_path}")
    print("")

    _log.info("AlienVox v%s starting — session %s", version, tel.session_id)
    tel.emit("app.start")

    cfg = load_effective_config()
    stacks = available_stacks()

    active_stack = cfg.get("engine", "sapi5")
    active_model = cfg.get("model", "")
    _log.info("active stack=%s model=%s", active_stack, active_model or "(none)")
    engine = _load_engine(active_stack, active_model)
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

    # ── Tray voice menu helpers ─────────────────────────────────────────────

    def _enumerate_voice_groups() -> list[dict]:
        """Build grouped voice data for the two-level tray Voice menu."""
        groups: list[dict] = []

        # SAPI stacks (Windows only)
        if sys.platform == "win32":
            sapi_defs = [
                ("sapi5",            "SAPI5",            "SapiEngine"),
                ("speech_platform",  "Speech Platform",  "SpeechPlatformEngine"),
            ]
            for sid, slabel, cls_name in sapi_defs:
                try:
                    if sid == active_stack and engine:
                        voices = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
                    else:
                        from .engines.sapi_win import SapiEngine, SpeechPlatformEngine  # noqa: F401
                        _cls = SapiEngine if cls_name == "SapiEngine" else SpeechPlatformEngine
                        voices = [{"id": v.id, "label": v.name} for v in _cls().list_voices()]
                except Exception:
                    voices = []
                if voices:
                    groups.append({"id": sid, "label": slabel, "voices": voices})

        # ML stack — one model sub-menu per installed model
        ml_models: list[dict] = []
        ml_model = active_model or "kokoro"
        if active_stack == "ml" and engine:
            try:
                ml_voices = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
            except Exception:
                ml_voices = get_voices("ml", ml_model)
        else:
            ml_voices = get_voices("ml", ml_model)
        if ml_voices:
            ml_models.append({"id": ml_model, "label": ml_model.title(), "voices": ml_voices})
        if ml_models:
            groups.append({"id": "ml", "label": "ML / AI", "models": ml_models})

        return groups

    def _refresh_tray_voices() -> None:
        groups = _enumerate_voice_groups()
        tray.populate_voice_menu(
            groups,
            current_voice_id=cfg.get("voice", ""),
            on_select=lambda sid, vid: _on_tray_voice_select(sid, vid),
        )

    def _on_tray_voice_select(stack_id: str, voice_id: str) -> None:
        if stack_id != active_stack:
            on_stack_changed(stack_id, voice_id)
        else:
            on_voice_changed(voice_id)
        tel.emit("config.changed", engine=stack_id, detail="voice")

    # ── Persistence callbacks ───────────────────────────────────────────────

    def on_voice_changed(vid: str) -> None:
        cfg["voice"] = vid  # update in-memory so next speak() picks it up immediately
        save_user_override({"voice": vid})
        _refresh_tray_voices()

    def on_stack_changed(new_stack_id: str, voice_id: str = "") -> None:
        """Called when the user switches engine tabs in the main window."""
        nonlocal engine, active_stack, active_model
        if new_stack_id == active_stack:
            return
        _log.info("stack switch: %s → %s", active_stack, new_stack_id)

        # Stop current engine before swapping
        if engine:
            try:
                engine.stop()
            except Exception:
                pass

        active_stack = new_stack_id
        # For ml stack, preserve model; for sapi stacks model is empty
        if new_stack_id == "ml":
            active_model = cfg.get("model", "") or "kokoro"
        else:
            active_model = ""

        cfg["engine"] = new_stack_id
        save_user_override({"engine": new_stack_id})

        engine = _load_engine(active_stack, active_model)
        if engine:
            _log.info("engine swapped: %s", type(engine).__name__)
        else:
            _log.warn("no engine for stack=%s", active_stack)

        if voice_id:
            cfg["voice"] = voice_id
            save_user_override({"voice": voice_id})

        _refresh_tray_voices()

    def on_config_saved(patch: dict[str, Any]) -> None:
        save_user_override(patch)

    def _do_stop() -> None:
        if engine:
            engine.stop()
        tray.set_idle()

    def _ensure_main_window() -> MainWindow:
        nonlocal _main_window
        if _main_window is None:
            # Populate voices for every available Windows SAPI stack so all tabs show
            # real voices, not just the active one.
            win_live_voices: dict[str, list[dict]] = {}

            # Active engine voices
            if engine:
                try:
                    vlist = [{"id": v.id, "label": v.name} for v in engine.list_voices()]
                    win_live_voices[active_stack] = vlist
                    _log.info("window: loaded %d voices for stack=%s", len(vlist), active_stack)
                except Exception as exc:
                    _log.warn("window: voice enumeration failed: %s", exc)

            # Always enumerate non-active SAPI stacks so their tabs aren't blank.
            if sys.platform == "win32":
                _sapi_stacks = {"sapi5", "speech_platform"} - {active_stack}
                for sid in _sapi_stacks:
                    try:
                        if sid == "sapi5":
                            from .engines.sapi_win import SapiEngine
                            _aux = SapiEngine()
                        else:
                            from .engines.sapi_win import SpeechPlatformEngine
                            _aux = SpeechPlatformEngine()
                        vlist = [{"id": v.id, "label": v.name} for v in _aux.list_voices()]
                        if vlist:
                            win_live_voices[sid] = vlist
                            _log.info("window: loaded %d voices for stack=%s (non-active)", len(vlist), sid)
                    except Exception as exc:
                        _log.warn("window: voice enum failed for stack=%s: %s", sid, exc)

            # ML voices from engine or stacks.yaml
            if active_stack == "ml" and not win_live_voices.get("ml"):
                try:
                    yaml_voices = get_voices("ml", active_model or "kokoro")
                    if yaml_voices:
                        win_live_voices["ml"] = yaml_voices
                except Exception:
                    pass

            _main_window = MainWindow(
                stacks=stacks,
                telemetry=tel,
                on_speak=speak_async,
                on_stop=_do_stop,
                on_voice_changed=on_voice_changed,
                on_config_saved=on_config_saved,
                on_about=open_about,
                on_stack_changed=on_stack_changed,
                live_voices=win_live_voices,
                current_voice_id=cfg.get("voice", ""),
                models_root=_models_root(),
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

    tray = AlienVoxTray(
        on_speak=speak_async,
        on_stop=_do_stop,
        on_settings=open_settings,
        on_about=open_about,
        on_quit=quit_app,
        on_window_toggle=toggle_window,
    )

    _refresh_tray_voices()

    tray.show()
    open_settings()  # show main window on startup

    # Spoken startup announcement — confirms audio pipeline is alive.
    if engine and active_stack in ("sapi5", "ml"):
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
