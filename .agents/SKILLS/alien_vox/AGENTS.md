# AGENTS.md — alien_vox skill

This folder is a **self-sufficient unit**: everything needed to run the AlienVox TTS skill lives
inside it. No sibling `../../../python_lib` or other repo-root dependency — `alienvox_tts` is
vendored directly at `./alienvox_tts/`.

## Copying this folder to a new machine/repo

1. Copy `.agents/SKILLS/alien_vox/` in full (including `alienvox_tts/`) — nothing outside this
   folder is required. Or run `python build.py` first and copy/unzip `.build/alien_vox.zip`
   instead, which already excludes dev-only files (`.venv/`, `__pycache__/`, etc).
2. Create a venv inside it and install deps:
   ```bat
   cd alien_vox
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r scripts/requirements.txt
   ```
3. Run `python -m pytest tests/ -v` to confirm the real test suite passes on the new machine (real
   Kokoro synthesis — no mocking).
4. Run `python scripts/speak.py "test"` to confirm real playback works.

## Why vendored instead of shared

`python_lib/` at the repo root still exists as the canonical, actively-developed copy of
`alienvox_tts`. This folder's `./alienvox_tts/` is a **deliberate, standalone copy** — the tradeoff
is duplication vs. the skill folder being truly portable (no relative-path `sys.path` reach into a
sibling folder three levels up that may not exist if this skill is copied elsewhere on its own).
When `alienvox_tts` changes in `python_lib/`, re-copy `python_lib/alienvox_tts/` over this folder's
`alienvox_tts/` and re-run the tests. `python_mcp_server/` keeps its own separate vendored copy for
the same reason.

## Conventions

- `scripts/speak.py` — the CLI wrapper; thin by design (arg parsing + reporting only), all real
  synthesis logic lives in `alienvox_tts/`.
- `alienvox_tts/` — the vendored TTS library (Kokoro-82M engine, `af_heart` default voice,
  CPU-default device policy, persistent volume state). See its own module docstrings for details.
- `references/voices.md` — voice roster, controls, and how to add another engine.
- `build.py` — packages this folder into `.build/alien_vox.zip` for deployment (see README.md).
- Anti-mocking test philosophy throughout (see `python_app/.agents/SKILLS/testing/SKILL.md` in
  this repo) — tests do real synthesis, no mocking internals.
