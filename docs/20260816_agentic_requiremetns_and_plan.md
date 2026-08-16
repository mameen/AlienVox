# Agentic Surfaces Requirements & Plan — `python_lib`, `alien_vox` Skill, `python_mcp_server`

**Date:** 2026-08-16
**Status:** Implemented and verified — `python_lib`, `.agents/SKILLS/alien_vox`, and
`python_mcp_server` all complete, real tests passing (see §7 below).
**Repo:** `C:\dev\personal\.repos\tts` (the first/canonical enlistment — confirmed by the user, not
the sibling `tts2` clone used for the majority of prior AlienVox app work)

---

## 1. Original requirements (verbatim, as given)

> C:\dev\personal\.repos\tts\README.md has amazing quality
>
> please read C:\dev\personal\.repos\tts\AGENTS.md
>
> especially Kokoro-82M / American F • Heart
>
> ----
> using this config as default (but configurable)
>
> ---
> I love to create both C:\dev\personal\.repos\tts\.agents\SKILLS\alien_vox following best
> practices and samples from C:\dev\personal\.agents\SKILLS and
> C:\dev\personal\.agents\SKILLS\README.md
>
> Create a self sufficient fully functioning alien_vox skill
>
> ---
> C:\dev\personal\.repos\tts\python_mcp_server python state of the art mcp server that supports
> both gpu / cpu (default cpu) and defaults to [the config above]
>
> ---
> as needed the scripts from both the skill and the MCP are free to call the top level
> ..\python_lib
>
> I don't intend to host this externally yet
>
> ---
> instead of breaking the already working app, we will copy out reusable composable OOP state of
> the art SDK + Lib that is verbosely documented inline in C:\dev\personal\.repos\tts\python_lib

Later clarification mid-turn: **"we will use the first enlistment from C:\dev\personal\.repos\tts"**
— confirming this repo (not `tts2`) is the target for all three new directories.

## 2. Derived requirements

1. **`python_lib/`** — a standalone, reusable, composable, OOP, verbosely inline-documented Python
   SDK, **copied out** of the already-working `python_app` (not a refactor of it — `python_app`
   must remain untouched and working exactly as it does today).
2. **`.agents/SKILLS/alien_vox/`** — a self-sufficient, fully-functioning Claude Code Skill, built
   following the conventions in `C:\dev\personal\.agents\SKILLS\README.md` (the Agent Skills
   authoring guide) and matching the style of this repo's existing sibling skills
   (`dev-vs-prod`, `highlevel_design`, `telemetry`, `testing`, `ui_ux_design`,
   `workspace-discipline`).
3. **`python_mcp_server/`** — a "state of the art" Python MCP server, supporting both CPU and GPU,
   **defaulting to CPU**.
4. **Default voice/engine, confirmed from `stacks.yaml`**: Kokoro-82M, voice `af_heart`
   ("American F · Heart") — the default, but configurable (callers can pick a different voice or,
   later, a different engine).
5. Both the skill's scripts and the MCP server are free to import/call the top-level `python_lib`
   directly (no packaging/publishing step required).
6. **Not intended to be hosted externally yet** — local-only, stdio-based MCP transport, no network
   exposure, no auth/hosting concerns to solve for in this pass.

## 3. Key facts gathered from exploration (grounding the plan below)

- `python_app/src/engines/base.py` — `TtsEngine` ABC (3 abstract methods: `list_voices`, `speak`,
  `stop`; 5 methods with defaults: `pause`, `resume`, `wait_until_done`, `synthesize`,
  `speak_sync`), plus `Voice`/`SpeakParams` dataclasses.
- `python_app/src/engines/kokoro_engine.py` — the flagship default engine. Uses `kokoro.KPipeline`
  (PyPI package `kokoro>=0.9.0`, no custom weights path — HF Hub caching is handled internally by
  `KPipeline(repo_id="hexgrad/Kokoro-82M")`), 7 voices, `_SAMPLE_RATE = 24_000`. Does **not** call
  the app's `device.select_device()` — device handling is left to `KPipeline`/torch internally.
- `python_app/src/device.py` — `select_device()`/`cuda_available()`, real `device_count() > 0`
  check (not just `torch.cuda.is_available()`, which can be misleadingly true with zero visible
  devices).
- `python_app/src/config.py::models_root()` — HARD RULE: dev always uses `<repo>/python_app/
  .models` unconditionally; frozen/installed always uses `%LOCALAPPDATA%\com.alientech.alienvox\
  .models`. **Not inherited by `python_lib`** — Kokoro's own engine never calls this function
  either (HF Hub's own cache handles it), so the new standalone SDK has zero dependency on the
  app's config system at all.
- `python_app/src/audio_player.py` — shared `play_audio()`/`stop_playback()` via `sounddevice`,
  including a real fix already found and shipped in the app: a `_PLAYBACK_TAIL_SETTLE_S` delay
  after `sd.wait()` (WASAPI hands back control before the hardware buffer tail has actually
  finished rendering — confirmed by ear, not theoretical).
- Other 8 engines exist in `python_app` (Piper, Chatterbox, Dia, F5-TTS, OuteTTS, VibeVoice,
  Qwen3-TTS, SAPI5) — **out of scope for this pass**, see Scope Decision below.
- Sibling skill frontmatter conventions (all 6 existing `.agents/SKILLS/*` dirs): `name`,
  `description`, `license: Apache-2.0`, `compatibility`, `metadata: {author: AlienTech.Software,
  version: "N.N"}`. Two of six have a `name` that doesn't match their directory name exactly
  (`highlevel_design` → `cross-platform-development`, `ui_ux_design` → `ui-ux-design`) — the new
  `alien_vox` skill's `name` will match its directory exactly, per the Agent Skills spec's actual
  requirement.
- `C:\dev\personal\.agents\SKILLS\README.md` states a preferred library version format —
  `major.minor.BUILD{YYYYMMDDHHmmss}`, starting at today's date at midnight if no prior version —
  but **none of the 6 existing sibling skills actually follow this** (all plain `"1.0"`-style
  strings). Decision: the new `alien_vox` skill follows the README's stated convention, since it's
  the documented preference and this is a fresh skill with no prior version to preserve
  compatibility with.
- Only one real local MCP server reference pattern found: `C:\dev\personal\.repos\tyco_runs_mcp\
  server.py` — official `mcp` Python SDK, `Server` + `stdio_server()`, `@app.list_tools()`/
  `@app.call_tool()` handlers, protocol plumbing (`server.py`) separated from domain logic
  (`mcp_tools/` package). No `fastmcp` usage found anywhere locally.
- `python_app/requirements.txt` pins: `torch>=2.0.0`, `transformers>=4.30.0`,
  `huggingface_hub[hf_xet]>=0.20.0`, `numpy>=1.24.0,<2.0.0` (capped for chatterbox-tts
  compatibility — not relevant to Kokoro-only scope, but kept as the shared floor/ceiling anyway
  for consistency), `soundfile>=0.12.1`, `sounddevice>=0.4.6`.

## 4. Scope decision for this pass

Porting all 9 `python_app` engines into `python_lib` in one pass would be a multi-day effort on its
own. **Decision (stated to the user in the plan, approved): port the shared architecture in full
(`base.py`, `device.py`, `audio.py`) and Kokoro as the one fully-working, default engine.** Kokoro
is both the confirmed default and the simplest engine to extract cleanly (plain PyPI package, no
custom weights path, no reference-audio/voice-cloning complexity unlike Chatterbox/F5-TTS/Dia). The
extension pattern (subclass `TtsEngine`, register in an `ENGINES` dict) is documented so adding
Piper/Chatterbox/etc. later is a small, well-defined addition, not a redesign.

## `python_lib/` — the shared SDK

Fully standalone — no dependency on `python_app`'s package, `config.py`, or `stacks.yaml`. Kokoro's
own engine in `python_app` doesn't call `models_root()` either (confirmed: `KPipeline` handles HF
Hub caching internally), so this decoupling costs nothing.

```
python_lib/
├── README.md                    # what this is, install, quick example
├── requirements.txt              # torch>=2.0.0, transformers>=4.30.0, kokoro>=0.9.0,
│                                  # numpy>=1.24.0,<2.0.0, soundfile>=0.12.1, sounddevice>=0.4.6
├── alienvox_tts/
│   ├── __init__.py              # public API: synthesize(), TtsEngine, Voice, SpeakParams, ENGINES
│   ├── base.py                  # TtsEngine ABC, Voice, SpeakParams — ported verbatim in shape,
│   │                             # verbosely documented (every method's contract explained inline)
│   ├── device.py                # select_device()/cuda_available() — ported verbatim
│   ├── audio.py                 # play_audio()/stop_playback() — ported, includes the
│   │                             # WASAPI-tail-settle fix already found for real in python_app
│   └── engines/
│       ├── __init__.py
│       └── kokoro.py            # KokoroEngine — adapted from python_app's kokoro_engine.py,
│                                 # decoupled from ..logger (use stdlib logging instead)
└── tests/
    └── test_kokoro.py           # real synthesis test (anti-mock philosophy, per testing/SKILL.md) —
                                  # skips gracefully if kokoro/torch aren't installed, real otherwise
```

Top-level convenience API (`alienvox_tts/__init__.py`):
```python
def synthesize(text: str, voice: str = "af_heart", engine: str = "kokoro",
                device: str | None = None) -> tuple[np.ndarray, int]:
    """device=None -> auto (select_device()); 'cpu'/'cuda' forces it."""
```

## `.agents/SKILLS/alien_vox/` — the Claude Code Skill

Matches sibling skill frontmatter conventions (Apache-2.0, `compatibility`, `metadata.author`) —
flagging one real drift found: the repo's own `.agents/SKILLS/README.md` states a preferred
`major.minor.BUILD{YYYYMMDDHHmmss}` version format, but none of the 6 existing sibling skills
actually follow it (all plain `"1.0"`-style strings). **This new skill will follow the README's
stated convention** (e.g. `0.1.<today's date at midnight, YYYYMMDD000000>`), since it's the
documented preference, even though older skills predate it.

```
.agents/SKILLS/alien_vox/
├── SKILL.md              # name: alien_vox (matches dir); description with trigger vocabulary
│                          # ("speak this text", "generate a voice sample", "text to speech")
├── scripts/
│   └── speak.py           # CLI: python speak.py "text" [--voice af_heart] [--device cpu] [--out file.wav]
│                           # imports ../../../python_lib (sys.path insert), thin wrapper only
├── references/
│   └── voices.md          # Kokoro's 7 voices, default af_heart, how to add engines later
└── assets/
    └── sample_af_heart.wav # generated for real during verification (not fabricated)
```

## `python_mcp_server/` — the MCP server

Uses the **official `mcp` Python SDK** (only real local reference pattern found:
`C:\dev\personal\.repos\tyco_runs_mcp\server.py` — `Server` + `stdio_server()`, `@app.list_tools()`/
`@app.call_tool()` handlers), stdio transport, protocol plumbing separated from domain logic
(mirroring that reference's `server.py` vs `mcp_tools/` split).

```
python_mcp_server/
├── README.md              # what it is, how to run, tool list
├── requirements.txt         # mcp>=1.0.0, plus python_lib's own requirements
├── server.py               # Server("alienvox-tts") + stdio_server() + list_tools/call_tool wiring
├── tools.py                 # tool schemas + handlers: speak_text, list_voices — imports python_lib
└── tests/
    └── test_tools.py        # real handler tests (no mocking python_lib itself)
```

**Tools exposed (v1):**
- `list_voices(engine: str = "kokoro")` — returns the voice roster.
- `speak_text(text: str, voice: str = "af_heart", engine: str = "kokoro", device: str = "cpu") ->
  path to a generated WAV file` — `device` param defaults to `"cpu"` explicitly (not auto-select),
  matching the confirmed "supports both CPU/GPU, defaults to CPU" requirement — `"gpu"` opts in.

Both `speak.py` (skill) and `server.py`/`tools.py` (MCP) import `python_lib` via a relative
`sys.path` insertion to the repo-root `python_lib/` directory (no packaging/install step required,
consistent with "free to call the top-level `../python_lib`").

## Verification

1. `pip install -r python_lib/requirements.txt` in a throwaway venv (or reuse `python_app`'s
   `.venv` — same pins) — real install, not just import checks.
2. `python python_lib/tests/test_kokoro.py` (or `pytest python_lib/tests/`) — real synthesis, real
   audio array returned, matches `python_app`'s existing anti-mock test philosophy.
3. `python .agents/SKILLS/alien_vox/scripts/speak.py "Welcome to AlienVox." --voice af_heart` —
   real CLI run, produces real audio (played and/or saved), generates `assets/sample_af_heart.wav`
   for real (not fabricated).
4. Start `python python_mcp_server/server.py`, drive it with a minimal stdio MCP client (or the
   `mcp` SDK's own dev/inspector tooling if available) to call `list_voices` and `speak_text` for
   real and confirm a real WAV comes back.
5. Confirm `python_app/` itself is untouched (`git status` clean there) — this is purely additive.

## 7. Real findings during implementation (not in the original plan)

- **`mcp` SDK 2.0 has a genuinely different API than the 1.x decorator style** most example code
  online (including the local `tyco_runs_mcp` reference used for the original design) still shows.
  The old `@app.list_tools()`/`@app.call_tool()` decorators on `mcp.server.Server` don't exist in
  2.0 — that class moved to a callback-registration constructor pattern instead. Discovered by
  actually installing `mcp` and introspecting the real package rather than trusting the reference
  example — confirmed via `pip show mcp` (version 2.0.0) and `inspect`/`grep` against the installed
  source. The correct modern API is `mcp.server.mcpserver.MCPServer` — the SDK's own high-level
  class, its native equivalent of what third-party `fastmcp` used to provide before the official
  SDK absorbed that ergonomic style. `requirements.txt` now pins `mcp>=2.0.0` (not `>=1.0.0`) with
  a comment explaining why.
- **`Tool.input_schema` is snake_case in this SDK version**, not the `inputSchema` camelCase used
  in older docs/examples — caught by a real test failure (`AttributeError`), not assumed.
- **User asked mid-implementation to also expose MCP resources and prompts**, not just tools (the
  original plan only covered tools) — added `alienvox://voices`/`alienvox://engines` resources and
  a `narrate` reusable prompt template, all verified working end-to-end with real data (not just
  "doesn't crash" — actual `call_tool`/`read_resource`/`get_prompt` calls were run and their real
  return values inspected).
- `python_mcp_server/tools.py` was deliberately restructured to have **zero `mcp` SDK imports** —
  pure functions (`do_list_voices`, `do_speak_text`, `do_list_engines`) that `server.py` wraps with
  thin `@app.tool()`/`@app.resource()`/`@app.prompt()` decorators. This means `tools.py`'s own
  tests never needed `mcp` installed at all (only `kokoro`), and if the SDK's API changes again,
  only `server.py`'s registration layer needs to change — not the actual TTS logic.

## 8. Verification actually performed (real, not just planned)

- `python_lib`: 13/13 real tests passed (real Kokoro synthesis, multiple voices, volume scaling,
  invalid-voice fallback) against `python_app`'s own venv (already had `kokoro`/`torch` installed).
- `alien_vox` skill: `scripts/speak.py` run for real, produced `assets/sample_af_heart.wav` (253KB,
  5.28s of real audio) — not fabricated.
- `python_mcp_server`: 11/11 real tests passed, PLUS a manual end-to-end smoke test calling
  `call_tool("speak_text", ...)`, `call_tool("list_engines", {})`, `read_resource("alienvox://voices")`,
  and `get_prompt("narrate", ...)` directly against the real running `MCPServer` instance, with
  real output inspected (a real WAV path, real JSON voice roster, real filled-in prompt text).
- `python_app/`: `git status --short python_app/` confirmed clean throughout — untouched.

