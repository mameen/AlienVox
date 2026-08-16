"""AlienVox MCP domain logic — pure Python, no `mcp` SDK imports here.

Deliberately kept free of any MCP-protocol types (Tool/Resource/Prompt
objects, TextContent, etc.) — `server.py` owns all of that, registering
thin decorated wrappers around the plain functions in this file. This
split means the actual TTS logic here can be unit-tested (and read) with
zero knowledge of the MCP protocol, and the protocol wiring in `server.py`
can be swapped/upgraded (as already happened once in this repo's history —
see `docs/20260816_agentic_requiremetns_and_plan.md`'s note on the `mcp`
SDK's 1.x -> 2.0 API change) without touching this file at all.

All real synthesis is delegated to `python_lib`'s `alienvox_tts`.

Device policy (explicit, not python_lib's own auto-detect default):
`speak_text`'s `device` argument defaults to `"cpu"` — this server does
NOT auto-prefer GPU just because one happens to be present, matching the
confirmed "supports both, defaults to CPU" requirement. Pass
`device="gpu"` to opt in explicitly.

Playback policy: `speak_text` plays audio directly through the local
default output device by default (`play=True`) — this MCP server is a
local stdio process, spawned by and running on the SAME machine as the
user, so there's a real speaker to play through; unlike a hosted/remote
server, generating a WAV file nobody will open is the wrong default here.
Pass `save=True` to also (or instead, with `play=False`) write a real
`.wav` file to `OUTPUT_DIR` when a file is actually wanted (e.g. to
attach/send somewhere).

Volume policy: `speak_text`'s `volume` argument defaults to `None`, which
uses the current PERSISTENT volume level (python_lib's
alienvox_tts.volume — a process-lifetime default that `set_volume`/
`volume_up`/`volume_down` below adjust) rather than resetting to 100 on
every call. Pass an explicit 0..100 to override just that one call
without touching the persistent level.
"""
from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

# python_lib lives one level up from this file (repo root -> python_lib).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "python_lib"))

from alienvox_tts import DEFAULT_VOICE, ENGINES, list_voices, synthesize  # noqa: E402
from alienvox_tts.audio import play_audio  # noqa: E402
from alienvox_tts.device import select_device  # noqa: E402
from alienvox_tts.volume import get_volume, set_volume, volume_down, volume_up  # noqa: E402

# Only used when save=True — otherwise no file ever touches disk.
OUTPUT_DIR = Path(tempfile.gettempdir()) / "alienvox_mcp_output"


def do_list_voices(engine: str = "kokoro") -> dict[str, Any]:
    """List every voice available for a given TTS engine."""
    if engine not in ENGINES:
        return {"error": f"Unknown engine {engine!r}. Available: {sorted(ENGINES)}"}
    voices = list_voices(engine)
    return {"engine": engine, "voices": [{"id": v.id, "name": v.name} for v in voices]}


def do_speak_text(
    text: str,
    voice: str = DEFAULT_VOICE,
    engine: str = "kokoro",
    device: str = "cpu",
    rate: int = 0,
    volume: int | None = None,
    play: bool = True,
    save: bool = False,
) -> dict[str, Any]:
    """Synthesize `text` and play it through the local default audio
    output device (play=True, the default — this server runs on the same
    machine as the user). Pass save=True to also write a real .wav file to
    OUTPUT_DIR (e.g. because the caller actually wants a file to attach
    somewhere) — independent of play, so save=True, play=False just writes
    a file with no audible playback."""
    if not text.strip():
        return {"error": "text is empty — nothing to speak."}
    if engine not in ENGINES:
        return {"error": f"Unknown engine {engine!r}. Available: {sorted(ENGINES)}"}

    resolved_device = select_device(prefer=device)
    effective_volume = get_volume() if volume is None else volume

    try:
        audio, sample_rate = synthesize(text, voice=voice, engine=engine, device=device, rate=rate, volume=volume)
    except Exception as exc:
        return {"error": f"synthesis failed: {exc}"}

    result: dict[str, Any] = {
        "sample_rate": sample_rate,
        "duration_s": round(len(audio) / sample_rate, 2),
        "voice": voice,
        "engine": engine,
        "device_requested": device,
        "device_used": resolved_device,
        "volume_used": effective_volume,
        "played": False,
    }

    if save:
        import soundfile as sf

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{voice}_{uuid.uuid4().hex[:8]}.wav"
        sf.write(str(out_path), audio, sample_rate)
        result["path"] = str(out_path)

    if play:
        # Blocks until playback (incl. the WASAPI tail-settle) finishes —
        # see alienvox_tts/audio.py's docstring for why the settle delay
        # exists (a real, confirmed-by-ear cutoff bug, not theoretical).
        play_audio(audio, sample_rate)
        result["played"] = True

    return result


def do_list_engines() -> dict[str, Any]:
    """List every registered TTS engine id (currently just 'kokoro' — see
    python_lib/alienvox_tts/engines/__init__.py for how to add more)."""
    return {"engines": sorted(ENGINES)}


def do_get_volume() -> dict[str, Any]:
    """Current persistent volume level (0..100), used by speak_text
    whenever its own `volume` argument is omitted."""
    return {"volume": get_volume()}


def do_set_volume(percent: int) -> dict[str, Any]:
    """Set the persistent volume level absolutely. Clamped to 0..100 —
    returns the value actually applied, which may differ from the
    requested one if it was out of range."""
    return {"volume": set_volume(percent)}


def do_volume_up(step: int = 10) -> dict[str, Any]:
    """Raise the persistent volume by `step` percentage points (default
    10), clamped at 100."""
    return {"volume": volume_up(step)}


def do_volume_down(step: int = 10) -> dict[str, Any]:
    """Lower the persistent volume by `step` percentage points (default
    10), clamped at 0."""
    return {"volume": volume_down(step)}
