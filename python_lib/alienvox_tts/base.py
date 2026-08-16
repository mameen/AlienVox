"""Abstract TTS engine protocol — every engine in this library implements this.

This is the same contract `python_app`'s desktop app engines follow
(`python_app/src/engines/base.py`), copied out and decoupled from the app's
own logger/config so `python_lib` has zero dependency on `python_app` and can
be used standalone by both the `alien_vox` Claude Skill and
`python_mcp_server`. If you change this file, the app's own copy is
NOT affected — and vice versa; the two are intentionally independent so
neither can accidentally break the other.

Why an ABC at all, instead of just a function per engine: every engine here
has genuinely different lifecycle needs (some load a multi-hundred-MB model
lazily on first use and cache it; some need to run playback on a background
thread so `speak()` can return immediately; some can capture raw audio
samples for export/return, some — historically, SAPI-style engines — can
only play audio directly and can't hand back a buffer). The ABC's job is to
give every engine the SAME shape for those differences, so a caller (the
skill's CLI, the MCP server's tool handler, or your own script) can treat
any engine identically:

    engine = KokoroEngine()
    audio, sample_rate = engine.synthesize("hello", "af_heart", SpeakParams())

works no matter which concrete engine class you're holding.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Voice:
    """One selectable voice within an engine.

    `id` is what you pass to `synthesize()`/`speak()` — it's engine-specific
    (Kokoro's are short codes like "af_heart"; other engines might use
    longer names). `name` is the human-readable label for display.
    """
    id: str
    name: str


@dataclass
class SpeakParams:
    """Playback/synthesis tuning knobs, uniform across every engine.

    Not every engine honors every field — an engine that has no pitch
    control (Kokoro, for instance) simply ignores `pitch` rather than
    erroring. This mirrors how physical hardware controls work: turning a
    knob that isn't wired to anything is a no-op, not a crash.

    `extra` exists for engine-specific controls that don't make sense as a
    universal field (e.g. a hypothetical noise-reduction strength some
    engine might expose) — keeps this dataclass from growing a field for
    every one-off engine quirk while still giving engines an escape hatch.
    """
    rate: int = 0        # -10 (slowest) .. 10 (fastest), 0 = engine's natural pace
    pitch: int = 0        # -10 (lowest) .. 10 (highest); ignored by engines with no pitch control
    volume: int = 100     # 0 (silent) .. 100 (full) — applied as a post-synthesis linear scale
    extra: dict[str, Any] = field(default_factory=dict)


class TtsEngine(ABC):
    """Every concrete engine (KokoroEngine, and whatever you add later)
    subclasses this. Three methods are mandatory; the rest have sensible
    defaults so a minimal engine implementation only needs to write three
    methods to be fully usable.
    """

    @abstractmethod
    def list_voices(self) -> list[Voice]:
        """Return every voice this engine can speak with. Called before
        showing a user/agent a choice, and to validate a requested voice_id
        exists before attempting synthesis."""
        ...

    @abstractmethod
    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Synthesize AND play `text` through the default audio output
        device. Returns immediately if the engine plays asynchronously (see
        `wait_until_done()`) — check each concrete engine's docstring for
        whether this call blocks."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Interrupt any in-progress speak() call — both the synthesis (if
        still running) and any audio currently playing. Must be safe to
        call even when nothing is speaking (a no-op in that case, not an
        error)."""
        ...

    def pause(self) -> None:
        """Pause playback. Default: no-op — override only if the engine's
        audio backend genuinely supports pause/resume (most streaming
        audio backends, including the one this library uses, don't; the
        practical alternative most engines take is to just stop())."""
        pass

    def resume(self) -> None:
        """Resume a paused speak() call. Default: no-op — see pause()."""
        pass

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Block until the current speak() call finishes (or times out).
        Returns True if it finished normally, False on timeout. Default
        implementation returns True immediately — correct for any engine
        whose speak() is itself synchronous/blocking; engines that speak()
        on a background thread MUST override this with a real wait."""
        return True

    def synthesize(
        self, text: str, voice_id: str, params: "SpeakParams"
    ) -> "tuple[Any, int] | None":
        """Return (float32 numpy array, sample_rate) WITHOUT playing audio
        — this is the hook that makes an engine usable for exporting to a
        file, returning audio bytes from an MCP tool, etc., rather than
        only ever playing through local speakers. Default returns None
        (meaning "this engine can't capture raw audio, only play it
        directly") — every engine in this library DOES implement this
        properly, since capturing audio without playing it is essential
        for a library/server context (an MCP server generally shouldn't be
        playing audio on whatever machine it happens to be running on)."""
        return None

    def speak_sync(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Convenience: speak() then block until done. Equivalent to
        calling both yourself — provided so simple scripts don't need to
        remember the two-call pattern."""
        self.speak(text, voice_id, params)
        self.wait_until_done()
