"""AlienVox entry point — PySide6 tray-first app.

Wires the MVC split: builds AppState (Model) once from the effective
config + catalog, builds AppController (the only thing that mutates
AppState), then constructs MainWindow and AlienVoxTray as Views that read
AppState and call AppController — nothing here holds engine/voice/model
state of its own anymore.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# Load .env (HUGGINGFACE_TOKEN, CUDA_VISIBLE_DEVICES, ...) before anything
# that might import torch. Loaded here directly (not just by run.py) so
# `python -m src.main` works standalone too, e.g. under a debugger.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import logger as _logger
from .config import load_effective_config
from .config import models_root as _models_root
from .control.app_controller import AppController
from .control.hotkey import enhanced_variant_of, start_listener
from .control.telemetry import Telemetry
from .engines.registry import available_stacks
from .model.app_state import AppState
from .version import version as get_version
from .view.main_window import MainWindow
from .view.tray import AlienVoxTray

_log = _logger.get_logger("main")


def _publish_aux_sapi_voices(state: AppState) -> None:
    """Enumerate voices for Windows SAPI stacks OTHER than the active one,
    so their main-window tabs aren't blank before the user ever switches
    to them. The active stack's voices are already published by
    AppController when it loads the engine."""
    if sys.platform != "win32":
        return
    for sid in ({"sapi5", "speech_platform"} - {state.active_stack}):
        try:
            if sid == "sapi5":
                from .engines.sapi_win import SapiEngine
                aux = SapiEngine()
            else:
                from .engines.sapi_win import SpeechPlatformEngine
                aux = SpeechPlatformEngine()
            voices = [{"id": v.id, "label": v.name} for v in aux.list_voices()]
            if voices:
                state.set_live_voices(sid, voices)
                _log.info("aux voices loaded: %d for stack=%s", len(voices), sid)
        except Exception as exc:
            _log.warn("aux voice enum failed for stack=%s: %s", sid, exc)


def _speak_startup(controller: AppController, voice_id: str) -> None:
    """Play a spoken startup announcement to confirm the audio pipeline is alive."""
    import time as _time
    _time.sleep(0.6)  # let the UI finish painting first
    if not controller.engine:
        return
    try:
        from .engines.base import SpeakParams
        controller.engine.speak(
            "AlienVox is ready. The dedicated audio engine is running.",
            voice_id,
            SpeakParams(),
        )
        _log.info("startup announcement spoken")
    except Exception as exc:
        _log.warn("startup announcement failed: %s", exc)


def main() -> int:
    # Single-instance guard — must run before anything else. One AlienVox
    # process total, regardless of --cpu/--gpu; switching device mode
    # requires closing the running instance first.
    from .single_instance import SingleInstanceGuard
    instance_guard = SingleInstanceGuard()
    if not instance_guard.acquired:
        msg = "AlienVox is already running. Close the running instance first."
        print(f"\n  {msg}\n")
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "AlienVox", 0x40)  # MB_ICONINFORMATION
            except Exception:
                pass
        return 1

    # Must run before any window is created — otherwise Windows groups the
    # taskbar entry under python.exe's own icon instead of AlienVox's,
    # since we're launched via `python -m src.main` rather than a
    # dedicated .exe (which would carry its own AppUserModelID for free).
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "AlienTech.AlienVox.App"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("AlienVox")
    app.setOrganizationName("AlienTech.Software")
    app.setQuitOnLastWindowClosed(False)
    _app_icon_path = Path(__file__).parent / "resources" / "icons" / "icon_256x256.png"
    if _app_icon_path.exists():
        app.setWindowIcon(QIcon(str(_app_icon_path)))

    tel = Telemetry()
    log_path = _logger.init(tel.session_id)

    # ── Startup banner (printed to stdout so `run.py app` shows it) ───────────
    import os
    version = get_version()
    print("")
    print(f"  AlienVox  v{version}")
    print(f"  PID     : {os.getpid()}")
    print(f"  Session : {tel.session_id}")
    print(f"  Log     : {log_path}")
    try:
        from .health import hardware_summary_lines
        for line in hardware_summary_lines():
            print(f"  {line}")
    except Exception as exc:
        print(f"  (hardware summary unavailable: {exc})")
    print("")

    _log.info("AlienVox v%s starting — session %s (PID %d)", version, tel.session_id, os.getpid())
    tel.emit("app.start")

    cfg = load_effective_config()
    stacks = available_stacks()

    state = AppState(stacks, cfg)
    _log.info("active stack=%s model=%s", state.active_stack, state.active_model or "(none)")

    debug = os.environ.get("ALIENVOX_DEBUG") == "1"
    if debug:
        _log.warn("debug mode ON — raw + enhanced text will be recorded in telemetry")

    controller = AppController(state, tel, extra_cfg=cfg, debug=debug)
    if controller.engine:
        _log.info("engine loaded: %s", type(controller.engine).__name__)
    else:
        _log.warn("no engine loaded for stack=%s", state.active_stack)

    _publish_aux_sapi_voices(state)

    _main_window: MainWindow | None = None

    def _ensure_main_window() -> MainWindow:
        nonlocal _main_window
        if _main_window is None:
            _main_window = MainWindow(
                app_state=state,
                controller=controller,
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

    def quit_app() -> None:
        controller.quit()
        hotkey_listener.stop()
        app.quit()

    tray = AlienVoxTray(
        state=state,
        controller=controller,
        on_quit=quit_app,
        on_window_toggle=toggle_window,
    )

    tray.show()
    open_settings()  # show main window on startup

    # Spoken startup announcement — confirms audio pipeline is alive.
    if controller.engine and state.active_stack in ("sapi5", "ml"):
        voice_id = state.voice
        if not voice_id:
            try:
                all_voices = controller.engine.list_voices()
                voice_id = all_voices[0].id if all_voices else ""
            except Exception:
                voice_id = ""
        threading.Thread(
            target=_speak_startup,
            args=(controller, voice_id),
            daemon=True,
        ).start()

    hotkey_listener = start_listener({
        state.hotkey: controller.speak_async,
        enhanced_variant_of(state.hotkey): controller.speak_enhanced_async,
    })

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
