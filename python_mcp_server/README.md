# AlienVox TTS MCP Server

A Model Context Protocol server exposing AlienVox's local Kokoro-82M TTS engine as MCP tools,
resources, and prompts. Stdio transport — not hosted externally (see
[`docs/20260816_agentic_requiremetns_and_plan.md`](../docs/20260816_agentic_requiremetns_and_plan.md)).

**Fully self-sufficient**: `alienvox_tts` is vendored directly inside this folder
(`./alienvox_tts/`) — no sibling `../python_lib` dependency. Copy `python_mcp_server/` alone to a
new machine and it runs; see `AGENTS.md` for the standalone-copy checklist.

Built on the official `mcp` Python SDK's high-level `MCPServer` class (`mcp.server.mcpserver`) —
its own native equivalent of what third-party `fastmcp` used to provide, confirmed via the
installed package rather than assumed (this SDK's 2.0 API is a real break from the older 1.x
decorator style most example code online still shows — see `requirements.txt`'s comment).

## Install

```bat
cd python_mcp_server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

That's the complete setup — `requirements.txt` lists every dependency this folder needs, including
the vendored `alienvox_tts` library's own deps (torch, kokoro, etc).

## Run

```bat
python run.py server
```

(Or `python server.py` directly, or `python run.py inspect` to launch the official MCP Inspector
against it — see `run.py`'s own docstring for why `inspect` doesn't just shell out to `mcp dev`.)

Speaks MCP over stdio — connect it from an MCP host (Claude Desktop, an IDE, etc.) by pointing it
at this command. Not meant to be run standalone and watched — it waits for a client to connect over
stdio and will appear to hang otherwise (that's correct behavior).

## What it exposes

### Tools

- **`speak_text(text, voice="af_heart", engine="kokoro", device="cpu", rate=0, volume=None, play=True, save=False)`**
  — synthesizes real speech and **plays it through the local default audio device by default**
  (this server runs on the same machine as the user — generating a WAV file nobody opens is the
  wrong default). Pass `save=True` to also write a real `.wav` file (its path is then returned);
  pass `play=False` to suppress playback. `device` defaults to `"cpu"` — pass `"gpu"` to opt into
  CUDA if present (falls back to CPU automatically if not). `volume=None` (default) uses the
  current **persistent** volume level — see below — pass an explicit `0..100` to override just
  that one call.
- **`list_voices(engine="kokoro")`** — the voice roster for an engine.
- **`list_engines()`** — every registered engine id (currently just `kokoro`).
- **`get_volume()`** / **`set_volume(percent)`** / **`volume_up(step=10)`** / **`volume_down(step=10)`**
  — a **persistent, process-lifetime** volume level (0..100), separate from `speak_text`'s own
  per-call `volume` argument. "Make it quieter" should stay quieter for the next request too, not
  reset — that's what these are for. `volume_up`/`volume_down` default to ±10 percentage points.

### Resources

- **`alienvox://voices`** — the same voice roster as `list_voices`, as a passively-readable
  resource (some MCP hosts surface resources differently from tools — e.g. in a context/file
  browser rather than requiring an explicit call).
- **`alienvox://engines`** — the same data as `list_engines`, as a resource.

### Prompts

- **`narrate(text, voice="af_heart")`** — a reusable prompt template so an MCP host can offer
  "narrate this text" as a one-click starting point that already knows to call `speak_text`,
  rather than requiring the request to be spelled out from scratch every time.

## Testing

```bat
python -m pytest tests/ -v
```

- `tests/test_tools.py` — real domain-logic tests (`tools.py` has zero `mcp` SDK imports, so these
  run even without `mcp` installed, only `kokoro`).
- `tests/test_server.py` — real registration/call tests against the installed `mcp` SDK, confirming
  tools/resources/prompts actually work end-to-end (not just that decoration doesn't crash).

Both follow the anti-mocking philosophy this repo uses throughout (see `python_app`'s
`.agents/SKILLS/testing/SKILL.md`) — no mocking `alienvox_tts` or the `mcp` SDK itself.

## Copying to another machine

See `AGENTS.md` for the full standalone-copy checklist — in short: copy this folder, create a venv
inside it, `pip install -r requirements.txt`, done.
