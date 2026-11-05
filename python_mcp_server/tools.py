"""AlienVox MCP domain logic — pure Python, no `mcp` SDK imports here.

Deliberately kept free of any MCP-protocol types (Tool/Resource/Prompt
objects, TextContent, etc.) — `server.py` owns all of that, registering
thin decorated wrappers around the plain functions in this file. This
split means the actual TTS logic here can be unit-tested (and read) with
zero knowledge of the MCP protocol, and the protocol wiring in `server.py`
can be swapped/upgraded (as already happened once in this repo's history —
see `docs/20260816_agentic_requiremetns_and_plan.md`'s note on the `mcp`
SDK's 1.x -> 2.0 API change) without touching this file at all.

All real synthesis is delegated to the vendored `alienvox_tts` package
(./alienvox_tts/ — a self-sufficient copy, no sibling ../python_lib
dependency).

Device policy (explicit, not alienvox_tts's own auto-detect default):
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
uses the current PERSISTENT volume level (the vendored
alienvox_tts.volume — a process-lifetime default that `set_volume`/
`volume_up`/`volume_down` below adjust) rather than resetting to 100 on
every call. Pass an explicit 0..100 to override just that one call
without touching the persistent level.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

# alienvox_tts is vendored directly inside this folder (see alienvox_tts/) —
# this server is meant to be self-sufficient: copy python_mcp_server/ alone
# to another machine, `pip install -r requirements.txt` in its own venv, and
# it runs, with no sibling ../python_lib dependency.
from alienvox_tts import DEFAULT_ENGINE, DEFAULT_VOICE, DEFAULT_VOICES, ENGINES, SpeakParams, get_engine, list_voices
from alienvox_tts.audio import play_audio
from alienvox_tts.device import select_device
from alienvox_tts.volume import get_volume, set_volume, volume_down, volume_up

# Only used when save=True — otherwise no file ever touches disk.
OUTPUT_DIR = Path(tempfile.gettempdir()) / "alienvox_mcp_output"


def do_list_voices(engine: str = DEFAULT_ENGINE) -> dict[str, Any]:
    """List every voice available for a given TTS engine."""
    if engine not in ENGINES:
        return {"error": f"Unknown engine {engine!r}. Available: {sorted(ENGINES)}"}
    voices = list_voices(engine)
    default_voice = DEFAULT_VOICES.get(engine)
    return {
        "engine": engine,
        "default_voice": default_voice,
        "voices": [{"id": v.id, "name": v.name, "is_default": v.id == default_voice} for v in voices],
    }


def do_speak_text(
    text: str,
    voice: str | None = None,
    engine: str = DEFAULT_ENGINE,
    device: str = "cpu",
    rate: int = 0,
    volume: int | None = None,
    play: bool = True,
    save: bool = False,
    language: str = "en",
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
    # MCP clients display the Piper default explicitly in their schema. If a
    # caller changes only the engine, translate that schema default to the
    # selected engine's own default voice.
    if not voice or (engine != DEFAULT_ENGINE and voice == DEFAULT_VOICE):
        voice = DEFAULT_VOICES.get(engine)
        if voice is None:
            return {"error": f"Choose an installed voice for engine {engine!r} with list_voices."}

    cpu_only = engine in {"piper", "supertonic3", "sapi5", "speech_platform"}
    resolved_device = "cpu" if cpu_only else select_device(prefer=device)
    effective_volume = get_volume() if volume is None else volume

    try:
        audio, sample_rate = get_engine(engine, resolved_device).synthesize(
            text, voice, SpeakParams(rate=rate, volume=effective_volume, extra={"lang": language})
        )
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
    """List engines with CPU/offline notes and preferred voices."""
    engines = [
        {"id": "kokoro", "name": "Kokoro-82M", "offline": True, "cpu_supported": True,
         "recommended_voices": ["af_heart", "af_bella", "bf_emma", "am_adam", "bm_george"]},
        {"id": "supertonic3", "name": "Supertonic 3", "offline": True, "cpu_supported": True,
         "recommended_voices": ["F1", "F4"], "notes": "Multilingual ONNX model; ~400 MB model files."},
        {"id": "piper", "name": "Piper", "offline": True, "cpu_supported": True,
         "recommended_voices": ["en_US-amy-medium", "en_US-lessac-medium", "en_GB-southern_english_female-low", "en_US-ryan-high"],
         "notes": "ONNX CPU inference; Amy Medium uses ~63 MB on disk. Warm synthesis: 0.421 s latency and 4.50 CPU-seconds per canonical sample, with a brief ~10.3-core burst."},
    ]
    if "sapi5" in ENGINES:
        engines.extend([
            {"id": "sapi5", "name": "Windows SAPI 5 / OneCore", "offline": True, "cpu_supported": True,
             "recommended_voices": ["MSTTS_V110_enUS_ZiraM", "MSTTS_V110_enGB_HazelM", "MSTTS_V110_enGB_SusanM", "TTS_MS_EN-US_ZIRA_11.0"],
             "notes": "Uses installed Windows voices; availability varies by machine."},
            {"id": "speech_platform", "name": "Microsoft Speech Platform", "offline": True, "cpu_supported": True,
             "recommended_voices": [], "notes": "Voices must be installed under Speech Server v11."},
        ])
    return {"engines": sorted(ENGINES), "details": engines}


def do_get_recommendations() -> dict[str, Any]:
    """Return subjective favorites and resource-aware alternatives."""
    return {
        "rating_basis": "Subjective developer listening preferences; not an objective benchmark.",
        "priority": ["low latency", "low CPU", "low memory"],
        "ml": [
            {"engine": "kokoro", "voices": ["af_heart", "af_bella", "bf_emma"], "note": "Favorite overall quality; shared model across voices and relatively memory-heavy."},
            {"engine": "kokoro", "voices": ["am_adam", "bm_george"], "note": "Developer described these as not too bad."},
            {"engine": "supertonic3", "voices": ["F1", "F4"], "note": "Top rated Supertonic voices; CPU ONNX and multilingual."},
            {"engine": "piper", "voices": ["en_US-lessac-medium", "en_US-amy-medium", "en_US-ryan-high", "en_US-kathleen-low", "en_GB-southern_english_female-low", "en_GB-jenny_dioco-medium"], "note": "All six are now developer favorites ('really good'). Historical listening scores were 5/5 for Ryan High and 4/5 for the other five; ONNX CPU inference."},
        ],
        "sapi": ["MSTTS_V110_enUS_ZiraM", "MSTTS_V110_enGB_HazelM", "MSTTS_V110_enGB_SusanM", "TTS_MS_EN-US_ZIRA_11.0"],
        "sapi_preferred_voice": "MSTTS_V110_enUS_ZiraM",
        "sapi_note": "MSTTS_V110_enUS_ZiraM is the SAPI-only performance recommendation (9.27 s versus 9.92 s for TTS_MS_EN-US_ZIRA_11.0 in the historical run); neither has a star rating, so this is not a quality verdict.",
        "local_models_dir": "Set ALIENVOX_MODELS_DIR to the folder containing ml\\piper and ml\\supertonic3; otherwise the app's per-user model directory is used.",
    }


def do_get_catalog() -> dict[str, Any]:
    """Return one client-friendly JSON catalog of engines, models, and voices."""
    details = do_list_engines()["details"]
    technology = {
        "kokoro": "PyTorch neural TTS",
        "piper": "ONNX neural TTS",
        "supertonic3": "ONNX multilingual neural TTS",
        "sapi5": "Installed Windows speech voices",
        "speech_platform": "Installed Microsoft Speech Platform voices",
    }
    model_sizes = {
        "en_US-ryan-high": 126,
        "en_US-kathleen-low": 63,
        "en_GB-southern_english_female-low": 63,
        "en_US-lessac-medium": 63,
        "en_US-amy-medium": 63,
        "en_GB-jenny_dioco-medium": 63,
        "en_GB-alan-medium": 63,
    }
    for item in details:
        item["technology"] = technology.get(item["id"], "local TTS")
        item["voices"] = do_list_voices(item["id"]).get("voices", [])
        item["default_voice"] = DEFAULT_VOICES.get(item["id"])
        if item["id"] == "piper":
            item["models"] = [
                {"id": voice["id"], "name": voice["name"], "format": "ONNX",
                 "approx_file_mb": model_sizes.get(voice["id"])}
                for voice in item["voices"]
            ]
        elif item["id"] == "kokoro":
            item["models"] = [{"id": "kokoro-82m", "name": item["name"], "format": "PyTorch",
                               "approx_file_mb": 327, "voice_ids": [v["id"] for v in item["voices"]]}]
        elif item["id"] == "supertonic3":
            item["models"] = [{"id": "supertonic3", "name": item["name"], "format": "ONNX",
                               "approx_files_mb": 400, "voice_ids": [v["id"] for v in item["voices"]]}]
        else:
            item["models"] = [
                {"id": voice["id"], "name": voice["name"], "format": "OS-installed voice"}
                for voice in item["voices"]
            ]
    return {
        "schema_version": 1,
        "default": {"engine": DEFAULT_ENGINE, "voice": DEFAULT_VOICE, "device": "cpu"},
        "trial_default": True,
        "tradeoff": {
            "voice": "en_US-amy-medium",
            "benchmark_phrase_chars": 123,
            "warm_latency_seconds": 0.4214,
            "warm_cpu_seconds": 4.5,
            "cpu_percent_one_core_equals_100": 1034.4,
            "model_file_mb": 63.1,
            "comparison": "Versus Kokoro af_heart: lower latency and total CPU time, with a brief higher-core-count burst; CPU-only, so it leaves the GPU available.",
            "benchmark_report": "python_mcp_server/reports/cpu-top-voices-20261105-125408/cpu-voice-cost.html",
        },
        "engines": details,
        "recommendations": do_get_recommendations(),
    }


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
