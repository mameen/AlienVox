# TODO #001: AlienVox python_app — Remaining Work

**Status:** Open  
**Created:** 2026-07-18  
**Component:** `python_app/`

> Replaces the old `gemini_poc`-scoped TODO. All gemini_poc items are closed.

---

## Current State (Stage 1 complete)

- PySide6 system tray with idle/speaking/error icon states.
- Right-click context menu: Speak Selection, Stop, Voice ▸, Settings…, About, Quit.
- Left-click triggers Speak Selection.
- About dialog.
- Four-layer YAML config (built-in defaults → stacks.yaml → user.yaml).
- Bundled `stacks.yaml` declares all stacks and models — no filesystem scanning.
- Telemetry: JSONL file sink + stderr `ALIENVOX_TELEMETRY` line per event.
- pynput global hotkey listener.
- Windows SAPI5 engine skeleton (sapi_win.py).
- 37 passing tests, ≥80% coverage on core logic modules.
- Text capture stub (audio not wired).

---

## Stage 2 — Windows APIs

- [ ] Real text capture: UIA → clipboard fallback (`capture.py`)
- [ ] SAPI5 engine: full speak/stop/pause/resume/voice-list via pywin32 COM
- [ ] Windows autostart (Registry `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run`)
- [ ] Hook global hotkey via pynput fully tested on Windows

## Stage 3 — ML Inference (in-process, no subprocess)

- [ ] Kokoro-82M: in-process inference via `kokoro` package
- [ ] Piper: in-process ONNX inference via `piper-tts`
- [ ] Dia: in-process via `dia` package
- [ ] VibeVoice: in-process via `transformers` + `torch`
- [ ] ML model install flow (download from HuggingFace Hub with progress)
- [ ] TTL-based model cache (keep model hot for N seconds after last use)

## Stage 4 — Testing Harness (Main Window)

- [ ] Balabolka-style main window: engine tabs, sliders, text canvas, playback toolbar
- [ ] All controls wired to config + telemetry
- [ ] Preferences / Settings panel (deferred from Stage 1)

## Stage 5 — Packaging

- [ ] PyInstaller single-file `.exe` build
- [ ] Windows NSIS per-user installer
- [ ] Icon baked into exe
- [ ] Auto-update mechanism (TBD)
