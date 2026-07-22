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
import re
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

# Characters not safe in a Windows filename — swapped for "_" when
# building export_default_name() (voice ids in particular can contain
# characters like ":" depending on the source engine).
_UNSAFE_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*]')

# Single source of truth for the "Play Sample" button and the performance
# test harness (tests/test_perf.py imports this rather than keeping its
# own copy) — both need the exact same phrase for results to be comparable.
SAMPLE_TEXT = (
    "Welcome to AlienVox. This is a performance test of your TTS engine. "
    "If you can hear this, your system is working correctly."
)

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
    "vibevoice_realtime": ("vibevoice_engine", "VibeVoiceEngine"),
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
    def __init__(
        self,
        state: AppState,
        telemetry: Telemetry,
        extra_cfg: dict[str, Any] | None = None,
        debug: bool = False,
    ) -> None:
        self.state = state
        self.telemetry = telemetry
        # Model-specific controls (Piper's noise_scale etc.) that don't live
        # on AppState's core fields — loaded once at startup from the
        # effective config and kept here rather than growing AppState with
        # per-model special cases.
        self._extra_cfg: dict[str, Any] = extra_cfg or {}
        # Debug mode (run.py app --debug): records raw + enhanced text in
        # telemetry's local JSONL sink. Off by default — normal telemetry
        # never records source text, only sizes (see SAMPLE_TEXT/enhance
        # docs in docs/issues/todo_004.md).
        self._debug = debug

        self.engine: "TtsEngine | None" = None
        self._speak_lock = threading.Lock()

        # Auto-persist and auto-reload-engine on every relevant state change.
        state.stack_changed.connect(self._on_stack_or_model_changed)
        state.model_changed.connect(self._on_stack_or_model_changed)
        state.voice_changed.connect(lambda _v: self._persist())
        state.params_changed.connect(lambda _p: self._persist())
        state.enhance_strategy_changed.connect(lambda _s: self._persist())

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

    def set_voice_enabled(self, stack_id: str, model_id: str, voice_id: str, enabled: bool) -> None:
        """User (un)checked a voice row in the Manage Voices dialog."""
        self.state.set_voice_enabled(stack_id, model_id, voice_id, enabled)
        self._persist()

    def select_enhance_strategy(self, strategy: str) -> None:
        """User flipped the global Enhanced toggle (toolbar). Global and
        persisted: every subsequent speak() call (Play, hotkey, tray) and
        export uses this strategy until toggled again — see speak()'s
        enhance=None default and apply_current_enhance() for export."""
        self.state.set_enhance_strategy(strategy)

    def apply_current_enhance(self, text: str) -> str:
        """Apply the current global enhance strategy to arbitrary text —
        used by the export path (Views build the text to synthesize
        themselves, so they call this before handing it to ExportDialog
        rather than going through speak())."""
        enhanced, _used = self._enhance_text(text, self.state.enhance_strategy)
        return enhanced

    def preview_voice_async(self, stack_id: str, model_id: str, voice_id: str) -> None:
        """Speak SAMPLE_TEXT with an arbitrary (stack, model, voice) —
        used by the Manage Voices dialog's per-row preview button. Unlike
        play_sample_async (which always uses the currently active
        engine/voice), this may target a voice that isn't active at all,
        so it never touches self.engine or AppState — it loads its own
        throwaway engine instance, speaks once, and discards it."""
        threading.Thread(
            target=self._preview_voice, args=(stack_id, model_id, voice_id), daemon=True
        ).start()

    def _preview_voice(self, stack_id: str, model_id: str, voice_id: str) -> None:
        if stack_id == self.state.active_stack and model_id == self.state.active_model and self.engine:
            # Already the active engine — reuse it rather than loading a
            # redundant second instance of the same model.
            engine = self.engine
            owns_engine = False
        else:
            engine = self._load_engine(stack_id, model_id)
            owns_engine = True
        if not engine:
            _log.warn("preview failed: no engine for stack=%s model=%s", stack_id, model_id)
            return
        try:
            self._run_engine_speak(
                engine, SAMPLE_TEXT, voice_id, SpeakParams(),
                stack_id=stack_id, model_id=model_id, source="preview",
                extra_triggered_fields={
                    "text_chars": len(SAMPLE_TEXT),
                    "text_bytes": len(SAMPLE_TEXT.encode()),
                },
            )
        except Exception as exc:
            _log.warn("preview_voice failed for %s/%s/%s: %s", stack_id, model_id, voice_id, exc)
        finally:
            if owns_engine:
                try:
                    engine.stop()
                except Exception:
                    pass

    def _run_engine_speak(
        self,
        engine: "TtsEngine",
        text: str,
        voice_id: str,
        params: SpeakParams,
        *,
        stack_id: str,
        model_id: str,
        source: str,
        request_id: str | None = None,
        extra_triggered_fields: dict[str, Any] | None = None,
    ) -> bool:
        """Shared engine.speak() + wait_until_done() + telemetry wrapper.

        Every command that triggers real speech (the main speak/hotkey
        path, Play Sample, and the Manage Voices dialog's per-row preview
        button) must go through this single place — not because telemetry
        is precious, but because it was previously duplicated inline in
        _speak_locked() only, and _preview_voice() called engine.speak()
        directly with no telemetry at all. That's exactly the kind of gap
        that's invisible until someone (a user in --debug mode) actually
        looks for the event and it isn't there. `source` distinguishes
        which command triggered it ("speak" vs "preview") in the JSONL
        without needing two near-duplicate sets of event names.

        Returns True if playback completed normally.
        """
        tel = self.telemetry
        rid = request_id or tel.new_request_id()
        start_ms = time.time_ns() // 1_000_000

        # text_chars/text_bytes are NOT auto-computed from `text` here — for
        # the real speak path, `text` at this point is already the enhanced
        # text (post text_enhancer), and text_chars historically means the
        # ORIGINAL pre-enhancement size (enhanced_chars is the separate,
        # explicit post-enhancement field). Auto-computing from `text` would
        # silently make text_chars/enhanced_chars measure the same thing.
        # Every caller must supply these via extra_triggered_fields.
        tel.emit(
            "speak.triggered",
            request_id=rid,
            source=source,
            engine=stack_id,
            model=model_id,
            voice=voice_id,
            rate=params.rate,
            pitch=params.pitch,
            volume=params.volume,
            version=get_version(),
            **(extra_triggered_fields or {}),
        )

        try:
            engine.speak(text, voice_id, params)

            tel.emit(
                "tts.first_audio",
                request_id=rid,
                source=source,
                engine=stack_id,
                model=model_id,
                latency_ms=time.time_ns() // 1_000_000 - start_ms,
                status="submitted",
            )

            completed = False
            try:
                completed = engine.wait_until_done(30_000)
            except Exception as exc:
                tel.emit("tts.error", request_id=rid, source=source, status="error",
                         detail=f"WaitUntilDone failed: {exc}")
                return False

            if completed:
                tel.emit("tts.playback_end", request_id=rid, source=source,
                         engine=stack_id, model=model_id, status="complete")
            else:
                tel.emit("tts.error", request_id=rid, source=source, status="timeout",
                         detail="WaitUntilDone timed out after 30s")

            tel.emit("speak.done", request_id=rid, source=source, engine=stack_id,
                     status="ok" if completed else "timeout")
            return completed
        except Exception as exc:
            tel.emit("tts.error", request_id=rid, source=source, status="error", detail=str(exc))
            tel.emit("speak.done", request_id=rid, source=source, engine=stack_id, status="error")
            raise

    def build_current_speak_params(self) -> SpeakParams:
        """SpeakParams for the currently active state — used by Views that
        need to construct a one-shot dialog (e.g. ExportDialog) without
        reaching into AppController's internals themselves."""
        return build_speak_params(self.state, self._extra_cfg)

    def export_default_name(self) -> str:
        """Default export filename stem (no extension):
        <session_id>_<play_id>_<stack>_<voice> — traceable back to the
        telemetry session, unique per export via a fresh request-style id,
        and identifies which stack/voice produced the audio at a glance."""
        play_id = self.telemetry.new_request_id()
        parts = [self.telemetry.session_id, play_id, self.state.active_stack, self.state.voice]
        return "_".join(_UNSAFE_FILENAME_CHARS_RE.sub("_", p) for p in parts if p)

    # ── Persistence ───────────────────────────────────────────────────────

    def _persist(self) -> None:
        save_user_override(self.state.to_cfg_patch())

    # ── Speak / stop ──────────────────────────────────────────────────────

    def speak(self, text: str | None = None, restart: bool = False, enhance: str | None = None) -> None:
        """Speak text — from provided string or captured selection.

        restart=False (hotkey/tray click default): acts as a toggle — if
        something is already speaking, this call just stops it.
        restart=True (main window Play button): interrupts any current
        playback and immediately speaks the new text, rather than
        requiring a second click to actually hear it.

        enhance: None (default) means "use the global Enhanced toggle"
        (state.enhance_strategy) — Play, the hotkey, and the tray all use
        this default, so flipping the toggle affects every speak path at
        once. Pass an explicit "none"/"heuristic"/"llm" to override the
        toggle for this call only — used by play_sample_async, which
        always stays unenhanced regardless of the toggle (it's a fixed
        diagnostic phrase, not user text).
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

    def _speak_locked(self, text: str | None, enhance: str | None = None) -> None:
        tel = self.telemetry
        rid = tel.new_request_id()
        self.state.set_speaking(True)

        if text is None:
            try:
                from .capture import get_selected_text
                text = get_selected_text()
            except ImportError:
                text = ""

        state = self.state
        # None means "use the global Enhanced toggle" — resolved here
        # (not in speak()) so every telemetry/log line downstream sees the
        # actual strategy, never the None sentinel.
        enhance = state.enhance_strategy if enhance is None else enhance
        original_chars, original_bytes = len(text), len(text.encode())
        enhanced_text, used_strategy = self._enhance_text(text, enhance)

        extra_fields: dict[str, Any] = {
            "hotkey": state.hotkey,
            "text_chars": original_chars,
            "text_bytes": original_bytes,
        }
        # Never record the source text itself — only sizes and strategy —
        # UNLESS the app was started with `run.py app --debug`, in which
        # case the whole point is to see what actually got said, including
        # what the enhancer changed. Debug mode is opt-in per launch, not
        # persisted, and the text still only reaches the local .logs/
        # JSONL sink (same as every other telemetry field).
        if enhance != "none":
            extra_fields["enhanced_chars"] = len(enhanced_text)
            extra_fields["enhanced_bytes"] = len(enhanced_text.encode())
            extra_fields["enhance_strategy"] = used_strategy
        if self._debug:
            extra_fields["text"] = text
            if enhance != "none":
                extra_fields["enhanced_text"] = enhanced_text
        text = enhanced_text

        try:
            if self.engine and text:
                params = build_speak_params(state, self._extra_cfg)
                completed = self._run_engine_speak(
                    self.engine, text, state.voice, params,
                    stack_id=state.active_stack, model_id=state.active_model,
                    source="speak", request_id=rid, extra_triggered_fields=extra_fields,
                )
                if not completed:
                    self.state.set_error("TTS playback failed or timed out")
            else:
                tel.emit(
                    "speak.triggered", request_id=rid, source="speak",
                    engine=state.active_stack, model=state.active_model, voice=state.voice,
                    **extra_fields,
                )
                tel.emit("speak.done", request_id=rid, source="speak",
                         engine=state.active_stack, status="skipped_no_engine_or_text")

            self.state.set_speaking(False)
        except Exception as exc:
            # Log, not just set_error() — a silent except here previously
            # masked a real TypeError (duplicate keyword arg) for the
            # entire "no engine" telemetry fallback path with zero visible
            # signal beyond AppState.error, which is easy to miss during
            # manual testing. See docs/issues/issue_003.md.
            _log.error("_speak_locked failed: %s", exc)
            self.state.set_error(str(exc))
            self.state.set_speaking(False)

    def speak_async(self, text: str | None = None) -> None:
        """Toggle behavior — used by the tray icon click and global hotkey.
        Respects the global Enhanced toggle (enhance=None default)."""
        threading.Thread(target=self.speak, args=(text, False), daemon=True).start()

    def play_async(self, text: str) -> None:
        """Restart behavior — used by the main window's Play button.
        Respects the global Enhanced toggle (enhance=None default)."""
        threading.Thread(target=self.speak, args=(text, True), daemon=True).start()

    def play_sample_async(self) -> None:
        """Speaks SAMPLE_TEXT with the active engine/voice — used by the
        main window's "Play Sample" button to let a user judge a voice
        without needing any text of their own. No hotkey (toolbar-only,
        deliberately not wired into hotkey.py). Always unenhanced
        (enhance="none" explicit override) — it's a fixed diagnostic
        phrase, testing/perf must stay deterministic regardless of the
        global toggle."""
        threading.Thread(
            target=self.speak, args=(SAMPLE_TEXT, True), kwargs={"enhance": "none"}, daemon=True
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
