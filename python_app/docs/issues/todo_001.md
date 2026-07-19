# TODO #001: AlienVox python_app — Remaining Work

**Status:** Open  
**Created:** 2026-07-18  
**Updated:** 2026-07-19  
**Component:** `python_app/`

> Replaces the old `gemini_poc`-scoped TODO. All gemini_poc items are closed.

---

## Current State (Stage 2 partially complete)

- PySide6 system tray with idle/speaking/error icon states.
- Right-click context menu: Speak Selection, Stop, Voice ▸, Settings…, About, Quit.
- Balabolka-style main window: engine tabs, sliders, text canvas, playback toolbar.
- About dialog (X button fixed, About toolbar button added).
- Four-layer YAML config (built-in defaults → stacks.yaml → user.yaml).
- Telemetry: JSONL file sink + stderr `ALIENVOX_TELEMETRY` line (4 events).
- pynput global hotkey listener.
- Text capture: WM_COPY tier-1 → Ctrl+C clipboard fallback.
- **SAPI5 engine: dedicated STA worker thread (matches Rust audio_win.rs).**
  - Single `alienvox-sapi` daemon thread owns ISpVoice for app lifetime.
  - Both Classic SAPI5 + OneCore hives enumerated → 11 voices visible.
  - Completion via `SpeakCompleteEvent` Win32 handle (not WaitUntilDone).
  - Pitch via SAPI native XML `<pitch absmiddle="N"/>` + `SPF_IS_XML` flag.
- 39 passing tests (SAPI engine fully covered).

---

## 🔴 Immediate / In-Progress

### Logging & Tracing (requested 2026-07-19)

Rust had per-session structured log files in `.telemetry/session-<ts>_AlienVox.log`.
Python only has the 4 telemetry events + a single `telemetry.jsonl` file.
User wants verbose `[TRACE]` / `[INFO]` / `[WARN]` / `[ERROR]` log lines to console
AND a per-session log file, separate from the concise telemetry JSONL.

- [ ] Add `src/logging_win.py` (or extend `telemetry.py`) with a structured logger
      that writes `[LEVEL] timestamp  component  message` lines to:
      - stderr (always)
      - `%LOCALAPPDATA%/com.alientech.alienvox/logs/session-<id>_AlienVox.log`
- [ ] On startup, print session ID and log file path to stdout (from `run.py app`)
- [ ] Replace bare `print(f"[SAPI] ...")` calls in `sapi_win.py` with logger calls
- [ ] Log format should mirror Rust: `[INFO]  2026-07-19T16:43:07  sapi  Speak() OK`

### Startup TTS Announcement (requested 2026-07-19)

User loved the announcement played during testing:
`"Hello from AlienVox. The dedicated STA worker thread is running."`

- [ ] Play a short startup announcement via SAPI on app launch (SAPI5 stack only)
- [ ] Announcement text TBD — something like "AlienVox is ready"
- [ ] Should fire after the main window is shown, on a daemon thread
- [ ] Include session ID + log file path in the printed startup banner (not spoken)

### Voice Dropdown Showing "(populated from OS at runtime)"

Active stack in user config is `ml` (not `sapi5`), so SAPI voices never load.
PiperEngine is partially implemented but model files are not downloaded.

- [ ] When active stack is `sapi5`, populate voice dropdown from `engine.list_voices()`
      at startup — this already works but the config must select `sapi5`
- [ ] Fix `user.yaml` / default config so `sapi5` is the default engine
- [ ] Show the actual voice name in the dropdown, not the placeholder string

### PiperEngine Missing `wait_until_done`

Telemetry shows: `'PiperEngine' object has no attribute 'wait_until_done'`

- [ ] Add `wait_until_done(timeout_ms)` to `TtsEngine` base class as a no-op default
- [ ] `PiperEngine` and any future ML engine inherits the no-op unless they override

---

## Stage 2 — Windows APIs

- [x] Real text capture: WM_COPY tier-1 → Ctrl+C clipboard fallback (`capture.py`)
- [x] SAPI5 engine: dedicated STA worker thread, full speak/stop/pause/resume/voice-list
- [x] Both SAPI5 + OneCore voice hives enumerated and deduplicated
- [x] Completion via SpeakCompleteEvent (Win32 HANDLE) — not WaitUntilDone(-1)
- [ ] Windows autostart (Registry `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`)
- [ ] Global hotkey fully tested on Windows (pynput)

## Stage 3 — ML Inference (in-process, no subprocess)

- [ ] Kokoro-82M: in-process inference via `kokoro` package
- [ ] Piper: in-process ONNX inference via `piper-tts`
- [ ] Dia: in-process via `dia` package
- [ ] VibeVoice: in-process via `transformers` + `torch`
- [ ] ML model install flow (download from HuggingFace Hub with progress)
- [ ] TTL-based model cache (keep model hot for N seconds after last use)
- [ ] `_load_engine()` dispatch for ML stack working end-to-end
- [ ] Voice dropdown populated from stacks.yaml for ML stack

## Stage 4 — Main Window Polish

- [/] Balabolka-style main window: engine tabs, sliders, text canvas, playback toolbar
- [ ] All controls wired to config + telemetry
- [ ] Preferences / Settings panel
- [x] Fix the OS close [X] button in AboutDialog
- [x] Add About button to toolbar

## Stage 5 — Packaging

- [ ] PyInstaller single-file `.exe` build
- [ ] Windows NSIS per-user installer
- [ ] Icon baked into exe
- [ ] Auto-update mechanism (TBD)
