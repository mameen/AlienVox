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

- [x] `src/logger.py` — structured `[LEVEL]  timestamp  component  message` logger
- [x] Per-session log file: `%LOCALAPPDATA%/com.alientech.alienvox/logs/session-<id>_AlienVox.log`
- [x] Startup banner prints session ID + log file path to stdout
- [x] `sapi_win.py` bare `print()` calls replaced with `_log.trace/info/warn/error`
- [x] Logger initialized from `tel.session_id` so logs and telemetry share the same session

### Startup TTS Announcement

- [x] `_speak_startup()` plays "AlienVox is ready. The dedicated audio engine is running."
- [x] Fires 0.6s after startup (daemon thread) so UI is visible first
- [x] SAPI5 stack only; picks first available voice if none configured

### Voice Dropdown "(populated from OS at runtime)"

- [x] Root cause: `user.yaml` had `engine: ml` overriding the `sapi5` default
- [x] Reset `user.yaml` to `engine: sapi5`
- [x] `wait_until_done` no-op default added to `TtsEngine` base class

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
