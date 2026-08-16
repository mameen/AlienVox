# AGENTS.md — python_mcp_server

This folder is a **self-sufficient unit**: everything needed to run the AlienVox TTS MCP server
lives inside it. No sibling `../python_lib` or other repo-root dependency — `alienvox_tts` is
vendored directly at `./alienvox_tts/`.

## Copying this folder to a new machine

1. Copy `python_mcp_server/` in full (including `alienvox_tts/`) to the new machine — nothing
   outside this folder is required.
2. Create a venv inside it and install deps:
   ```bat
   cd python_mcp_server
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run `python run.py test` to confirm the real test suite passes on the new machine (real Kokoro
   synthesis, real MCP SDK registration — no mocking).
4. Run `python run.py server` to start it, or point an MCP host (Claude Desktop, an IDE, etc.) at
   `<this-folder>\.venv\Scripts\python.exe server.py`.

## Why vendored instead of shared

`python_lib/` at the repo root still exists as the canonical, actively-developed copy of
`alienvox_tts` (used directly by the `alien_vox` skill's own vendored copy's upstream source, and
kept as a reference implementation). This folder's `./alienvox_tts/` is a **deliberate, standalone
copy** — the tradeoff is duplication vs. the folder being truly portable (no relative-path
`sys.path` reach into a sibling folder that may not exist on a fresh checkout of just this
directory). When `alienvox_tts` changes in `python_lib/`, re-copy `python_lib/alienvox_tts/` over
this folder's `alienvox_tts/` and re-run `python run.py test`.

## Conventions

- `tools.py` — pure domain logic, zero `mcp` SDK imports (testable without the SDK installed).
- `server.py` — MCP protocol registration only, delegates to `tools.py`.
- `alienvox_tts/` — vendored TTS library (Kokoro-82M engine, `af_heart` default voice, CPU-default
  device policy, persistent volume state). See its own module docstrings for details.
- Anti-mocking test philosophy throughout (see `python_app/.agents/SKILLS/testing/SKILL.md` in this
  repo for the rationale) — tests do real synthesis and real MCP SDK calls, no mocking internals.
