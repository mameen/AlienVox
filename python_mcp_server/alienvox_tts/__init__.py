"""alienvox_tts — a standalone, reusable, OOP Python TTS SDK.

Extracted from the AlienVox desktop app (`python_app/`) as a copy — this
library has zero dependency on `python_app`'s package, config system, or
`stacks.yaml`, so it can be used from anywhere: the `alien_vox` Claude Code
Skill, `python_mcp_server`, or your own scripts.

Quick start:

    from alienvox_tts import synthesize
    audio, sample_rate = synthesize("Hello, world!")   # Kokoro, af_heart, CPU (the real default)

    import soundfile as sf
    sf.write("out.wav", audio, sample_rate)

Or use an engine directly for more control (multiple calls reuse the same
loaded model instead of reloading it every time — see `ENGINES`):

    from alienvox_tts import KokoroEngine, SpeakParams
    engine = KokoroEngine()  # device="cpu" by default — see KokoroEngine's own docstring
    audio, sample_rate = engine.synthesize("Hello!", "af_heart", SpeakParams())

Default engine: Kokoro-82M. Default voice: `af_heart` ("American F ·
Heart") — matches the AlienVox app's own `stacks.yaml` default. Default
device: CPU, everywhere — an explicit `device="gpu"`/`"cuda"` opt-in is
required to use a GPU (matches AlienVox's own project-wide CPU-first
default; see `KokoroEngine`'s docstring for why this differs from
`device.select_device()`'s own auto-prefer-GPU behavior, which is a
different, lower-level building block, not this module's own default
policy). All configurable per call, never hardcoded past this module's
defaults.
"""
from __future__ import annotations

from .base import SpeakParams, TtsEngine, Voice
from .device import cuda_available, select_device
from .engines import KokoroEngine
from .volume import get_volume, set_volume, volume_down, volume_up

# Engine registry — the extension point for adding more engines later (see
# engines/__init__.py's docstring for the exact steps). Keyed by the same
# short id used throughout AlienVox's own stacks.yaml ("kokoro", "piper", …)
# so tooling built against this library and the app agree on naming.
ENGINES: dict[str, type[TtsEngine]] = {
    "kokoro": KokoroEngine,
}

DEFAULT_ENGINE = "kokoro"
DEFAULT_VOICE = "af_heart"  # American F · Heart
DEFAULT_DEVICE = "cpu"      # project-wide CPU-first default — see module docstring

# Process-lifetime engine instances, keyed by (engine_id, resolved_device)
# — created lazily on first use and reused after that. Keyed by device too
# (not just engine id): an engine's device is fixed at construction (see
# KokoroEngine's docstring — a loaded model can't cheaply move devices),
# so asking for "kokoro on cpu" and later "kokoro on gpu" in the same
# process must genuinely load two separate model instances, not silently
# hand back whichever one happened to load first.
_engine_instances: dict[tuple[str, str], TtsEngine] = {}


def get_engine(engine: str = DEFAULT_ENGINE, device: str = DEFAULT_DEVICE) -> TtsEngine:
    """Return the shared instance of the named engine on the given device,
    constructing it on first call for that (engine, device) pair. Raises
    KeyError with a helpful message for an unknown engine id — never
    silently falls back to a different engine."""
    if engine not in ENGINES:
        raise KeyError(
            f"Unknown engine {engine!r}. Available: {sorted(ENGINES)}. "
            "See engines/__init__.py's docstring to add a new one."
        )
    resolved_device = select_device(prefer=device)
    key = (engine, resolved_device)
    if key not in _engine_instances:
        _engine_instances[key] = ENGINES[engine](device=resolved_device)
    return _engine_instances[key]


def list_voices(engine: str = DEFAULT_ENGINE) -> list[Voice]:
    """List every voice available for the given engine. Device-agnostic —
    the voice roster doesn't depend on which device the model runs on, so
    this uses the default-device engine instance regardless."""
    return get_engine(engine).list_voices()


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    engine: str = DEFAULT_ENGINE,
    *,
    device: str = DEFAULT_DEVICE,
    rate: int = 0,
    pitch: int = 0,
    volume: int | None = None,
) -> tuple["object", int]:
    """Synthesize `text` and return (float32 numpy array, sample_rate)
    WITHOUT playing it — the convenience entry point for scripts, the
    Claude Skill, and the MCP server, all of which want raw audio to save
    or return rather than immediate local playback.

    device="cpu" (default): the real, enforced default — pass "gpu"/"cuda"
    to opt into CUDA (falls back to CPU automatically if unavailable).
    See KokoroEngine's docstring for why this module defaults to CPU
    rather than device.select_device()'s own auto-prefer-GPU behavior.

    volume=None (default): uses the current persistent volume level (see
    volume.py's get_volume()/set_volume() — a process-lifetime default,
    not reset per call). Pass an explicit 0..100 to override just this one
    call without touching the persistent level.

    Raises RuntimeError if the engine produced no audio (e.g. empty text
    after whitespace stripping) — callers should treat this as a real
    failure, not silently ignore it.
    """
    eng = get_engine(engine, device)
    effective_volume = get_volume() if volume is None else volume
    result = eng.synthesize(text, voice, SpeakParams(rate=rate, pitch=pitch, volume=effective_volume))
    if result is None:
        raise RuntimeError(
            f"{engine!r} engine produced no audio for the given text/voice={voice!r} "
            "(empty text, or an internal synthesis failure — check logs)."
        )
    return result


def speak(
    text: str,
    voice: str = DEFAULT_VOICE,
    engine: str = DEFAULT_ENGINE,
    *,
    device: str = DEFAULT_DEVICE,
    rate: int = 0,
    pitch: int = 0,
    volume: int | None = None,
    wait: bool = True,
) -> None:
    """Synthesize AND play `text` through the local default audio output
    device. wait=True (default) blocks until playback finishes; wait=False
    returns immediately (call get_engine(engine).wait_until_done() later
    if you need to block after the fact).

    device="cpu" (default) and volume=None (persistent level) — see
    synthesize()'s docstring for both."""
    eng = get_engine(engine, device)
    effective_volume = get_volume() if volume is None else volume
    params = SpeakParams(rate=rate, pitch=pitch, volume=effective_volume)
    if wait:
        eng.speak_sync(text, voice, params)
    else:
        eng.speak(text, voice, params)


__all__ = [
    "SpeakParams",
    "TtsEngine",
    "Voice",
    "KokoroEngine",
    "ENGINES",
    "DEFAULT_ENGINE",
    "DEFAULT_VOICE",
    "DEFAULT_DEVICE",
    "cuda_available",
    "select_device",
    "get_engine",
    "list_voices",
    "synthesize",
    "speak",
    "get_volume",
    "set_volume",
    "volume_up",
    "volume_down",
]
