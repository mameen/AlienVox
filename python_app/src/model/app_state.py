"""AppState — single source of truth for AlienVox's runtime configuration.

This is the "Model" in the MVC split introduced to fix a recurring bug
class: Views (MainWindow, AlienVoxTray) used to receive one-shot snapshot
values at construction time (current_voice_id, active_stack_id,
active_model_id, ...) plus a grab-bag of individual callbacks
(on_voice_changed, on_model_changed, on_stack_changed, ...). Nothing kept
the View's displayed state and the Controller's actual state in sync after
construction — e.g. the model dropdown always showed stacks.yaml's first
catalog entry, completely independent of which model was actually active,
because there was no single place both sides could read from.

AppState fixes this structurally: it's the ONLY place stack/model/voice/
rate/pitch/volume/speaking status live. Views read from it directly and
connect to its Qt signals to stay in sync; they never hold their own copy.
The Controller (AppController) is the only thing that mutates it. Views
call Controller methods; they never write to AppState directly either —
this keeps the data flow one-directional and traceable:

    View event -> Controller method -> AppState mutation -> signal ->
    every View's slot updates itself

AppState itself has no PySide6 widget dependencies and no business logic
(no engine loading, no speak orchestration) — it's a plain data holder
with signals, safe to unit test without a running engine.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from ..engines.registry import StackInfo


class AppState(QObject):
    """Single source of truth for AlienVox's active stack/model/voice/params.

    Every mutation goes through a setter method (not direct attribute
    assignment) so the corresponding Qt signal always fires — Views rely
    on this to stay in sync without polling.
    """

    stack_changed = Signal(str)                 # new active_stack
    model_changed = Signal(str)                 # new active_model
    voice_changed = Signal(str)                 # new voice_id
    params_changed = Signal(dict)                # {"rate"/"pitch"/"volume": value, ...}
    speaking_changed = Signal(bool)              # True while audio is playing
    error_changed = Signal(str)                  # non-empty message on error, "" to clear
    catalog_changed = Signal()                   # stacks/live_voices data replaced wholesale

    def __init__(self, stacks: list[StackInfo], cfg: dict[str, Any]) -> None:
        super().__init__()
        self._stacks = stacks
        self._live_voices: dict[str, list[dict]] = {}

        self._active_stack: str = cfg.get("engine", "sapi5")
        self._active_model: str = cfg.get("model", "")
        self._voice: str = cfg.get("voice", "")
        self._rate: int = cfg.get("rate", 0)
        self._pitch: int = cfg.get("pitch", 0)
        self._volume: int = cfg.get("volume", 100)
        self._hotkey: str = cfg.get("hotkey", "<ctrl>+<esc>")
        self._ttl_seconds: int = cfg.get("ttl_seconds", 30)
        self._speaking: bool = False
        self._last_error: str = ""

    # ── Read-only catalog data (static per process, not user state) ─────────

    @property
    def stacks(self) -> list[StackInfo]:
        return self._stacks

    def live_voices_for(self, stack_id: str) -> list[dict]:
        return self._live_voices.get(stack_id, [])

    def set_live_voices(self, stack_id: str, voices: list[dict]) -> None:
        self._live_voices[stack_id] = voices
        self.catalog_changed.emit()

    def stack_info(self, stack_id: str) -> StackInfo | None:
        return next((s for s in self._stacks if s.id == stack_id), None)

    def model_info(self, stack_id: str, model_id: str):
        stack = self.stack_info(stack_id)
        if stack is None:
            return None
        return next((m for m in stack.models if m.id == model_id), None)

    # ── Active stack/model/voice ──────────────────────────────────────────

    @property
    def active_stack(self) -> str:
        return self._active_stack

    def set_active_stack(self, stack_id: str) -> None:
        if stack_id == self._active_stack:
            return
        self._active_stack = stack_id
        self.stack_changed.emit(stack_id)

    @property
    def active_model(self) -> str:
        return self._active_model

    def set_active_model(self, model_id: str) -> None:
        if model_id == self._active_model:
            return
        self._active_model = model_id
        self.model_changed.emit(model_id)

    @property
    def voice(self) -> str:
        return self._voice

    def set_voice(self, voice_id: str) -> None:
        if voice_id == self._voice:
            return
        self._voice = voice_id
        self.voice_changed.emit(voice_id)

    # ── Rate/pitch/volume/ttl ─────────────────────────────────────────────

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def pitch(self) -> int:
        return self._pitch

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def set_params(self, **kwargs: int) -> None:
        """Batch-update rate/pitch/volume/ttl_seconds; emits one signal
        with only the keys that actually changed."""
        changed: dict[str, int] = {}
        for key, value in kwargs.items():
            attr = f"_{key}"
            if not hasattr(self, attr):
                raise ValueError(f"unknown param {key!r}")
            if getattr(self, attr) != value:
                setattr(self, attr, value)
                changed[key] = value
        if changed:
            self.params_changed.emit(changed)

    # ── Hotkey ────────────────────────────────────────────────────────────

    @property
    def hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey: str) -> None:
        self._hotkey = hotkey

    # ── Transient runtime status (not persisted) ─────────────────────────

    @property
    def speaking(self) -> bool:
        return self._speaking

    def set_speaking(self, speaking: bool) -> None:
        if speaking == self._speaking:
            return
        self._speaking = speaking
        self.speaking_changed.emit(speaking)

    @property
    def last_error(self) -> str:
        return self._last_error

    def set_error(self, message: str) -> None:
        self._last_error = message
        self.error_changed.emit(message)

    # ── Snapshot for persistence/telemetry ───────────────────────────────

    def to_cfg_patch(self) -> dict[str, Any]:
        """Everything that should be persisted to user.yaml."""
        return {
            "engine": self._active_stack,
            "model": self._active_model,
            "voice": self._voice,
            "rate": self._rate,
            "pitch": self._pitch,
            "volume": self._volume,
            "hotkey": self._hotkey,
            "ttl_seconds": self._ttl_seconds,
        }

    def load_cfg_patch(self, patch: dict[str, Any]) -> None:
        """Apply an external config patch (e.g. from Load Settings),
        firing the same signals a normal mutation would."""
        if "engine" in patch:
            self.set_active_stack(patch["engine"])
        if "model" in patch:
            self.set_active_model(patch["model"])
        if "voice" in patch:
            self.set_voice(patch["voice"])
        param_keys = ("rate", "pitch", "volume", "ttl_seconds")
        params = {k: patch[k] for k in param_keys if k in patch}
        if params:
            self.set_params(**params)
        if "hotkey" in patch:
            self.set_hotkey(patch["hotkey"])
