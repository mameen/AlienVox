"""AppController — the only thing that mutates AppState.

Owns the live TtsEngine instance, orchestrates speak/stop, and persists
every AppState change to user.yaml automatically (by subscribing to
AppState's own signals) — no call site can forget to save, unlike the
previous main.py closures where persistence was a manual
`save_user_override(...)` call duplicated in half a dozen places.

Reloading the engine on stack/model change is likewise automatic (also via
signal subscription) rather than something each caller had to remember —
this structurally closes the bug class where a UI control updated
AppState-equivalent data without the engine ever actually swapping.

Views (MainWindow, AlienVoxTray) call methods on this class in response to
user input; they never mutate AppState directly and never touch engine
loading themselves.
"""
from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..engines.base import TtsEngine

from .. import logger as _logger_mod
from ..config import save_user_override, user_yaml_path
from ..engines.base import SpeakParams
from ..model.app_state import AppState
from ..version import version as get_version
from . import text_enhancer
from .telemetry import Telemetry

_log = _logger_mod.get_logger("controller")

# Model-specific controls (beyond rate/pitch/volume) that get forwarded into
# SpeakParams.extra when the given model is active. Keys must match both the
# cfg dict AppState.to_cfg_patch() would produce and stacks.yaml's per-model
# controls.
_MODEL_EXTRA_CONTROL_KEYS: dict[str, list[str]] = {
    "piper": ["noise_scale", "noise_w", "sentence_silence"],
}

_ML_ENGINES: dict[str, tuple[str, str]] = {
    "kokoro":     ("kokoro_engine",     "KokoroEngine"),
    "piper":      ("piper_win",         "PiperEngine"),
    "chatterbox": ("chatterbox_engine", "ChatterboxEngine"),
    "dia":        ("dia_engine",        "DiaEngine"),
    "f5tts":      ("f5tts_engine",      "F5TTSEngine"),
    "outetts":    ("outetts_engine",    "OuteTTSEngine"),
}


def build_speak_params(state: AppState, extra_cfg: dict[str, Any] | None = None) -> SpeakParams:
    """Build SpeakParams from AppState, including model-specific extra
    controls (e.g. Piper's noise_scale) sourced from extra_cfg (the raw
    effective-config dict, since those controls aren't part of AppState's
    core rate/pitch/volume)."""
    extra: dict[str, Any] = {}
    extra_cfg = extra_cfg or {}
    for key in _MODEL_EXTRA_CONTROL_KEYS.get(state.active_model, []):
        if key in extra_cfg:
            extra[key] = extra_cfg[key]
    return SpeakParams(rate=state.rate, pitch=state.pitch, volume=state.volume, extra=extra)


class AppController:
    def __init__(self, state: AppState, telemetry: Telemetry, extra_cfg: dict[str, Any] | None = None) -> None:
        self.state = state
        self.telemetry = telemetry
        # Model-specific controls (Piper's noise_scale etc.) that don't live
        # on AppState's core fields — loaded once at startup from the
        # effective config and kept here rather than growing AppState with
        # per-model special cases.
        self._extra_cfg: dict[str, Any] = extra_cfg or {}

        self.engine: "TtsEngine | None" = None
        self._speak_lock = threading.Lock()

        # Auto-persist and auto-reload-engine on every relevant state change.
        state.stack_changed.connect(self._on_stack_or_model_changed)
        state.model_changed.connect(self._on_stack_or_model_changed)
        state.voice_changed.connect(lambda _v: self._persist())
        state.params_changed.connect(lambda _p: self._persist())

        self._load_engine_for_current_state()

    # ── Engine lifecycle ──────────────────────────────────────────────────

    def _load_engine(self, stack_id: str, model_id: str = "") -> "TtsEngine | None":
        """Return a live TtsEngine for the given stack/model, or None."""
        if sys.platform == "win32":
            if stack_id == "sapi5":
                try:
                    from ..engines.sapi_win import SapiEngine
                    return SapiEngine()
                except Exception as exc:
                    _log.error("SapiEngine init failed: %s", exc)
                    return None
            if stack_id == "speech_platform":
                try:
                    from ..engines.sapi_win import SpeechPlatformEngine
                    return SpeechPlatformEngine()
                except Exception as exc:
                    _log.warn("SpeechPlatformEngine init failed (runtime not installed?): %s", exc)
                    return None
        if stack_id == "ml":
            model = model_id or "kokoro"
            if model in _ML_ENGINES:
                module_name, class_name = _ML_ENGINES[model]
                try:
                    mod = importlib.import_module(f".engines.{module_name}", package=__package__.rsplit(".", 1)[0])
                    cls = getattr(mod, class_name)
                    eng = cls()
                    _log.info("%s loaded", class_name)
                    return eng
                except Exception as exc:
                    _log.error("%s init failed: %s", class_name, exc)
                    return None
            _log.warn("ML model=%r not recognised", model)
            return None
        return None

    def _load_engine_for_current_state(self) -> None:
        self.engine = self._load_engine(self.state.active_stack, self.state.active_model)
        if self.engine:
            _log.info("engine loaded: %s", type(self.engine).__name__)
            self._publish_live_voices(self.state.active_stack)
        else:
            _log.warn("no engine loaded for stack=%s", self.state.active_stack)

    def _publish_live_voices(self, stack_id: str) -> None:
        """Push the active engine's real voice list into AppState so Views
        refresh their combos — replaces the old update_voices()/
        update_sapi_voices() push methods called ad hoc from main.py."""
        if not self.engine:
            return
        try:
            voices = [{"id": v.id, "label": v.name} for v in self.engine.list_voices()]
            if voices:
                self.state.set_live_voices(stack_id, voices)
        except Exception as exc:
            _log.warn("voice enumeration failed for stack=%s: %s", stack_id, exc)

    def _on_stack_or_model_changed(self, _value: str) -> None:
        """Fires on EITHER stack_changed or model_changed — reloading the
        engine is identical either way, and this being automatic (rather
        than each View having to remember to call something) is exactly
        what closes the "model switched but engine didn't reload" bug
        class for good."""
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass
        self._load_engine_for_current_state()
        self._persist()

    def select_stack(self, stack_id: str, voice_id: str = "") -> None:
        """User switched engine tabs (main window) or picked a voice under
        a different stack (tray menu)."""
        if stack_id == self.state.active_stack:
            if voice_id:
                self.state.set_voice(voice_id)
            return
        _log.info("stack switch: %s -> %s", self.state.active_stack, stack_id)
        # For the ml stack, preserve/restore a model; other stacks have none.
        if stack_id == "ml":
            model_id = self.state.active_model or "kokoro"
        else:
            model_id = ""
        self.state.set_active_stack(stack_id)
        self.state.set_active_model(model_id)
        if voice_id:
            self.state.set_voice(voice_id)

    def select_model(self, model_id: str, voice_id: str = "") -> None:
        """User switched ML model (main window model dropdown or tray)."""
        if self.state.active_stack != "ml" or model_id == self.state.active_model:
            if voice_id:
                self.state.set_voice(voice_id)
            return
        _log.info("model switch: %s -> %s", self.state.active_model, model_id)
        self.state.set_active_model(model_id)
        if voice_id:
            self.state.set_voice(voice_id)

    def select_voice(self, voice_id: str) -> None:
        self.state.set_voice(voice_id)

    def update_params(self, **kwargs: int) -> None:
        """Rate/pitch/volume/ttl_seconds changes from sliders."""
        self.state.set_params(**kwargs)

    def build_current_speak_params(self) -> SpeakParams:
        """SpeakParams for the currently active state — used by Views that
        need to construct a one-shot dialog (e.g. ExportDialog) without
        reaching into AppController's internals themselves."""
        return build_speak_params(self.state, self._extra_cfg)

    # ── Persistence ───────────────────────────────────────────────────────

    def _persist(self) -> None:
        save_user_override(self.state.to_cfg_patch())

    # ── Speak / stop ──────────────────────────────────────────────────────

    def speak(self, text: str | None = None, restart: bool = False, enhance: str = "none") -> None:
        """Speak text — from provided string or captured selection.

        restart=False (hotkey/tray click default): acts as a toggle — if
        something is already speaking, this call just stops it.
        restart=True (main window Play button): interrupts any current
        playback and immediately speaks the new text, rather than
        requiring a second click to actually hear it.

        enhance: "none" | "heuristic" | "llm" — applied to this call only,
        not persisted anywhere on AppState. There is no "enhance mode"
        toggle; each caller (play_async vs play_enhanced_async) decides
        per call, matching the two distinct toolbar buttons.
        """
        if not self._speak_lock.acquire(blocking=False):
            self.stop()
            if not restart:
                return
            if not self._speak_lock.acquire(timeout=5.0):
                return
        try:
            self._speak_locked(text, enhance)
        finally:
            self._speak_lock.release()

    def _enhance_text(self, text: str, strategy: str) -> tuple[str, str]:
        """Apply the requested enhance strategy, falling back to heuristic
        (never to raw unenhanced text — the user opted into enhancement)
        if the LLM strategy fails for any reason. Returns (text, strategy
        actually used) so callers/telemetry can tell a fallback happened."""
        if strategy == "none" or not text:
            return text, strategy
        if strategy == "heuristic":
            return text_enhancer.heuristic_enhance(text), "heuristic"
        if strategy == "llm":
            try:
                return text_enhancer.llm_enhance(text), "llm"
            except Exception as exc:
                _log.warn("llm_enhance failed, falling back to heuristic: %s", exc)
                return text_enhancer.heuristic_enhance(text), "llm_fallback_heuristic"
        _log.warn("unknown enhance_strategy=%r, skipping enhancement", strategy)
        return text, "none"

    def _speak_locked(self, text: str | None, enhance: str = "none") -> None:
        tel = self.telemetry
        rid = tel.new_request_id()
        start_ms = time.time_ns() // 1_000_000
        self.state.set_speaking(True)

        if text is None:
            try:
                from .capture import get_selected_text
                text = get_selected_text()
            except ImportError:
                text = ""

        state = self.state
        original_chars, original_bytes = len(text), len(text.encode())
        enhanced_text, used_strategy = self._enhance_text(text, enhance)

        telemetry_fields: dict[str, Any] = {
            "text_chars": original_chars,
            "text_bytes": original_bytes,
        }
        # Never record the source text itself — only sizes and strategy.
        if enhance != "none":
            telemetry_fields["enhanced_chars"] = len(enhanced_text)
            telemetry_fields["enhanced_bytes"] = len(enhanced_text.encode())
            telemetry_fields["enhance_strategy"] = used_strategy
        text = enhanced_text

        tel.emit(
            "speak.triggered",
            request_id=rid,
            engine=state.active_stack,
            model=state.active_model,
            voice=state.voice,
            rate=state.rate,
            pitch=state.pitch,
            volume=state.volume,
            hotkey=state.hotkey,
            version=get_version(),
            **telemetry_fields,
        )

        try:
            if self.engine and text:
                params = build_speak_params(state, self._extra_cfg)
                self.engine.speak(text, state.voice, params)

                tel.emit(
                    "tts.first_audio",
                    request_id=rid,
                    engine=state.active_stack,
                    model=state.active_model,
                    latency_ms=time.time_ns() // 1_000_000 - start_ms,
                    status="submitted_to_sapi",
                )

                completed = False
                try:
                    completed = self.engine.wait_until_done(30_000)
                except Exception as exc:
                    tel.emit("tts.error", request_id=rid, status="error",
                             detail=f"WaitUntilDone failed: {exc}")
                    self.state.set_error(str(exc))

                if completed:
                    tel.emit("tts.playback_end", request_id=rid, engine=state.active_stack,
                             model=state.active_model, status="complete")
                else:
                    tel.emit("tts.error", request_id=rid, status="timeout",
                             detail="WaitUntilDone timed out after 30s")
                    self.state.set_error("TTS playback timed out")

            self.state.set_speaking(False)
            tel.emit("speak.done", request_id=rid, engine=state.active_stack, status="ok")
        except Exception as exc:
            tel.emit("tts.error", status="error", detail=str(exc))
            self.state.set_error(str(exc))
            self.state.set_speaking(False)

    def speak_async(self, text: str | None = None) -> None:
        """Toggle behavior — used by the tray icon click and global hotkey."""
        threading.Thread(target=self.speak, args=(text, False), daemon=True).start()

    def speak_enhanced_async(self, text: str | None = None) -> None:
        """Toggle behavior with heuristic text enhancement applied — used
        by the "Play Enhanced" global hotkey (primary hotkey + Shift, see
        hotkey.enhanced_variant_of). Captures the current selection when
        text is None, same as speak_async."""
        threading.Thread(
            target=self.speak, args=(text, False), kwargs={"enhance": "heuristic"}, daemon=True
        ).start()

    def play_async(self, text: str) -> None:
        """Restart behavior — used by the main window's Play button."""
        threading.Thread(target=self.speak, args=(text, True), daemon=True).start()

    def play_enhanced_async(self, text: str) -> None:
        """Restart behavior with heuristic text enhancement applied —
        used by the main window's dedicated "Play Enhanced" button.
        A one-shot action, not a persisted mode: the regular Play button
        is unaffected and always speaks text as-is."""
        threading.Thread(
            target=self.speak, args=(text, True), kwargs={"enhance": "heuristic"}, daemon=True
        ).start()

    def stop(self) -> None:
        if self.engine:
            self.engine.stop()
        self.state.set_speaking(False)

    # ── Settings save/load ────────────────────────────────────────────────

    def save_settings_to(self, path: Path) -> None:
        """Export the current user.yaml to an arbitrary path."""
        import shutil
        src = user_yaml_path()
        if src.exists():
            shutil.copy(src, path)
        else:
            save_user_override({}, user_file=Path(path))
        _log.info("settings saved to %s", path)
        self.telemetry.emit("config.changed", detail="settings_saved")

    def load_settings_from(self, path: Path) -> None:
        """Import settings from an arbitrary YAML file and apply them
        immediately — reloads engine/voice as needed via the normal
        AppState signal chain, so no separate "resync the UI" step is
        needed; every View already listens for these signals."""
        import yaml as _yaml
        with open(path, encoding="utf-8") as f:
            loaded = _yaml.safe_load(f) or {}

        save_user_override(loaded)
        self.state.load_cfg_patch(loaded)
        _log.info("settings loaded from %s", path)
        self.telemetry.emit("config.changed", detail="settings_loaded")

    # ── Shutdown ──────────────────────────────────────────────────────────

    def quit(self) -> None:
        self._persist()
        self.telemetry.emit("app.quit")
        if self.engine:
            self.engine.stop()
