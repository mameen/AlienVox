#!/usr/bin/env python
"""AlienVox TTS MCP Server — entry point.

Uses `mcp.server.mcpserver.MCPServer` (the SDK's high-level, decorator-based
API — the low-level `mcp.server.Server` class in this SDK version, 2.0,
uses a different callback-registration pattern entirely; verified directly
against the installed package rather than assumed, since community example
code online overwhelmingly targets the older 1.x decorator API that no
longer applies here).

Exposes all four MCP primitives relevant to this server:
  - **Tools** — `speak_text` (plays through local speakers by default),
    `list_voices`, `list_engines`, and persistent volume control
    (`get_volume`/`set_volume`/`volume_up`/`volume_down` — a
    process-lifetime default level, separate from `speak_text`'s own
    per-call `volume` override; see `tools.py`'s module docstring).
  - **Resources** — `alienvox://voices` and `alienvox://engines`: the same
    information as the list_* tools, but as passively-readable resources
    (some MCP hosts surface resources differently from tools — e.g. showing
    them in a file/context browser rather than requiring an explicit call).
  - **Prompts** — `narrate`: a reusable prompt template so an MCP host can
    offer "narrate this text" as a one-click starting point that already
    knows to call `speak_text`, rather than a user having to write that
    request from scratch every time.

Architecture: protocol registration (this file) is kept separate from the
actual TTS logic (`tools.py`, which has zero `mcp` SDK imports) — mirrors
the split in `C:\\dev\\personal\\.repos\\tyco_runs_mcp\\server.py` +
`mcp_tools/`, adapted for this SDK version's registration style.

Transport: stdio (the standard for an MCP server driven by a local host
application — Claude Desktop, an IDE, etc.). Not intended to be exposed
over a network — see docs/20260816_agentic_requiremetns_and_plan.md,
requirement #6: "not intended to be hosted externally yet".
"""
from __future__ import annotations

import asyncio
import json

from mcp.server.mcpserver import MCPServer

# alienvox_tts is vendored directly inside this folder (./alienvox_tts/) —
# this server is self-sufficient, no sibling ../python_lib dependency.
from alienvox_tts import DEFAULT_ENGINE, DEFAULT_VOICE

import tools

app = MCPServer(
    "alienvox-tts",
    version="0.1.0",
    instructions=(
        "Local, offline text-to-speech via Kokoro, Supertonic 3, Piper, and on Windows installed SAPI voices. "
        "Default voice: Kokoro af_heart, the developer's overall quality favorite. Piper en_US-amy-medium is available when low latency and total CPU use are the priority. Default device: CPU "
        "— pass device='gpu' to speak_text to use CUDA if available. "
        "speak_text plays through local speakers by default (pass save=True "
        "for a .wav file instead/as well). Volume is a persistent, process-"
        "lifetime level — set_volume/volume_up/volume_down adjust it; "
        "speak_text's own volume argument only overrides a single call. "
        "If the text to speak contains code blocks, ask the user first "
        "whether they want the code read aloud literally or replaced with "
        "a spoken 'code block' placeholder — don't guess, since reading "
        "source code character-by-character is rarely what's wanted."
    ),
)


# ── Tools ────────────────────────────────────────────────────────────────

@app.tool()
def speak_text(
    text: str,
    voice: str = DEFAULT_VOICE,
    engine: str = DEFAULT_ENGINE,
    device: str = "cpu",
    rate: int = 0,
    volume: int | None = None,
    play: bool = True,
    save: bool = False,
    language: str = "en",
) -> dict:
    """Synthesize text to speech using an AlienVox local offline engine
    (Kokoro, Supertonic 3, Piper, or installed Windows SAPI voices) and play it through the local default
    audio device (play=True, the default — this server runs on the same
    machine as the user). Default engine and voice: Kokoro af_heart.
    If you change only the engine, that engine's own default voice is selected automatically.
    Default device: CPU; Piper and Supertonic always use CPU. Other supported
    engines can opt into GPU with device='gpu'. volume=None (the
    default) uses the current persistent volume level — see
    get_volume/set_volume/volume_up/volume_down — pass an explicit 0..100
    to override just this call. Pass save=True to also write a real .wav
    file (its path is returned) — useful when a file is actually wanted,
    e.g. to attach somewhere. If `text` contains code blocks, ask the user
    first whether to read the code literally or substitute a spoken 'code
    block' placeholder — don't guess. For Supertonic 3, language is its
    language code (31 languages) or 'na' for the language-agnostic fallback."""
    return tools.do_speak_text(text, voice, engine, device, rate, volume, play, save, language)


@app.tool()
def list_voices(engine: str = DEFAULT_ENGINE) -> dict:
    """List every voice available for a given TTS engine. Default engine
    is the current default engine, Kokoro."""
    return tools.do_list_voices(engine)


@app.tool()
def list_engines() -> dict:
    """List available local engines, CPU support, preferred voices, and resource notes."""
    return tools.do_list_engines()


@app.tool()
def get_recommendations() -> dict:
    """Get subjective top voices and CPU/resource-aware alternatives, including Windows SAPI candidates."""
    return tools.do_get_recommendations()


@app.tool()
def get_tts_catalog() -> dict:
    """Return one JSON catalog with technologies, models, voices, defaults, and measured resource trade-offs."""
    return tools.do_get_catalog()


@app.tool()
def get_volume() -> dict:
    """Get the current persistent volume level (0..100) — the default
    speak_text uses whenever its own volume argument is omitted."""
    return tools.do_get_volume()


@app.tool()
def set_volume(percent: int) -> dict:
    """Set the persistent volume level absolutely (0..100, clamped).
    Affects every subsequent speak_text call that doesn't pass its own
    explicit volume override."""
    return tools.do_set_volume(percent)


@app.tool()
def volume_up(step: int = 10) -> dict:
    """Raise the persistent volume level by `step` percentage points
    (default 10), clamped at 100."""
    return tools.do_volume_up(step)


@app.tool()
def volume_down(step: int = 10) -> dict:
    """Lower the persistent volume level by `step` percentage points
    (default 10), clamped at 0."""
    return tools.do_volume_down(step)


# ── Resources ────────────────────────────────────────────────────────────

@app.resource("alienvox://voices", name="Offline voice rosters", mime_type="application/json")
def voices_resource() -> str:
    """Voice rosters for registered engines, as a passively-readable resource
    (same data as the list_voices tool — offered both ways since some MCP
    hosts surface resources differently from tools, e.g. in a context/file
    browser rather than requiring an explicit tool call)."""
    return json.dumps({engine: tools.do_list_voices(engine) for engine in __import__("alienvox_tts").ENGINES}, indent=2)


@app.resource("alienvox://engines", name="Registered TTS engines", mime_type="application/json")
def engines_resource() -> str:
    """Every registered TTS engine id, as a passively-readable resource."""
    return json.dumps(tools.do_list_engines(), indent=2)


@app.resource("alienvox://catalog", name="TTS technology and model catalog", mime_type="application/json")
def catalog_resource() -> str:
    """Full client-readable engine/model/voice catalog and trial-default tradeoff."""
    return json.dumps(tools.do_get_catalog(), indent=2)


@app.resource("alienvox://recommendations", name="Developer voice recommendations", mime_type="application/json")
def recommendations_resource() -> str:
    """Subjective listening favorites and CPU/resource-aware alternatives."""
    return json.dumps(tools.do_get_recommendations(), indent=2)


# ── Prompts ──────────────────────────────────────────────────────────────

@app.prompt()
def narrate(text: str, voice: str = DEFAULT_VOICE) -> str:
    """Reusable prompt template: narrate a piece of text aloud using
    AlienVox. Lets an MCP host offer "narrate this" as a one-click starting
    point that already knows to call speak_text with the right arguments,
    rather than requiring the user to spell out the request from scratch
    every time."""
    return (
        f"Use the speak_text tool to narrate the following text aloud, "
        f"using voice '{voice}':\n\n{text}"
    )


async def _main() -> None:
    await app.run_stdio_async()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\nAlienVox MCP server stopped", file=sys.stderr)
    except Exception as exc:
        print(f"Server error: {exc}", file=sys.stderr)
        sys.exit(1)
