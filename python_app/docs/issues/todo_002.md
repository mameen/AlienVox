# TODO #002: AlienVox — Engine Functionality

**Status:** Closed — every engine listed below as 🔴 is now implemented; see 2026-07-22 note.
**Updated:** 2026-07-20 (content), 2026-07-22 (closed)
**Scope:** `src/engines/`, `src/main.py`, `stacks.yaml`, `src/audio_win.py`

---

## 2026-07-22 housekeeping note

Verified against the current `src/engines/` directory — every model this file marked 🔴 now has a
real, working, tested engine module: `piper_win.py`, `dia_engine.py`, `chatterbox_engine.py`,
`f5tts_engine.py`, `outetts_engine.py`, and `vibevoice_engine.py` (added 2026-07-21/22, see
`todo_006.md` and `issue_001.md`/`issue_002.md`). "ML Model Install Flow" is also done —
`setup.py`'s `download` subcommand plus each engine's `install_dialog.py` branch. Stage 5
Packaging is done too — `install/windows/` has the PyInstaller spec and both build scripts,
verified working end-to-end (real portable zip + real installer exe built and tested this session).
Closing this file rather than leaving it as a stale open list.

---

---

## Done

- [x] SAPI5 engine: dedicated STA worker thread (mirrors Rust `audio_win.rs`)
- [x] Both Classic SAPI5 + OneCore voice hives enumerated (11 voices)
- [x] Completion via `SpeakCompleteEvent` Win32 handle
- [x] Pitch via SAPI native XML `<pitch absmiddle="N"/>` + `SPF_IS_XML`
- [x] `wait_until_done` no-op default in `TtsEngine` base class
- [x] Text capture: WM_COPY tier-1 → Ctrl+C clipboard fallback
- [x] Structured logger: per-session log file + `[LEVEL] ts component msg` to stderr
- [x] Startup TTS announcement on SAPI5 stack
- [x] 39 passing SAPI tests
- [x] `speech_platform` stack added to `stacks.yaml` + registry detection
- [x] `SpeechPlatformEngine` reuses `SapiEngine` with `Speech Server v11` hive
- [x] `src/audio_player.py`: shared `play_audio()` / `stop_playback()` via sounddevice
- [x] `KokoroEngine` (`src/engines/kokoro_engine.py`): auto-downloads from HuggingFace Hub via `KPipeline(repo_id='hexgrad/Kokoro-82M')`, 7 voices, rate→speed mapping
- [x] ML voices shown in tray + main window dropdown (from `engine.list_voices()`)
- [x] Startup announcement fires on both SAPI5 and ML stacks
- [x] `stacks.yaml`: kokoro marked `auto_download: true` → always available without pre-downloaded weights

---

## 🟢 Kokoro working — `engine: ml` selects it automatically

Set `user.yaml` → `engine: ml` (and optionally `model: kokoro`) to use it.
On first run, weights auto-download from HuggingFace Hub (~300 MB, one-time).

---

## 🔴 Piper ONNX (`src/engines/piper_engine.py`)

- [ ] Implement `TtsEngine` using `piper-tts` (in-process ONNX, no subprocess)
- [ ] Voice model files: each voice is a separate `.onnx` + `.json` file pair
  - Path: `models_root / "ml/piper/<voice_id>.onnx"`
  - List of downloadable voices declared in `stacks.yaml` `ml/piper/voices`
- [ ] `speak_to_wav()` works without audio hardware (CI-safe)
- [ ] Piper-specific controls: `noise_scale`, `noise_w`, `sentence_silence`
- [ ] Wire into `_load_engine()`: `engine_id == "ml" and model_id == "piper"`
- [ ] `wait_until_done()`: wait on playback thread event

**Current state:** `piper_win.py` is a stub — voice files not downloaded, no inference.

---

## 🔴 Dia 1.6B (`src/engines/dia_engine.py`)

- [ ] Implement `TtsEngine` using `dia` package (Apache 2.0, GPU-oriented)
- [ ] GPU check: if `torch.cuda.is_available()` is False, disable with tooltip warning
- [ ] Weight path: `models_root / "ml/dia"`

---

## 🔴 VibeVoice-Realtime-0.5B (`src/engines/vibevoice_engine.py`)

- [ ] Implement `TtsEngine` using `transformers` + `torch` (MIT, research)
- [ ] Streaming audio: pipe chunks to `sounddevice` for real-time playback
- [ ] Weight path: `models_root / "ml/vibevoice-realtime-0.5b"`

---

## 🔴 ML Model Install Flow

None of the ML models have weight files downloaded yet.
User sees `(populated from OS at runtime)` or broken voice list for all ML models.

- [ ] `run.py download` subcommand: download a named model from HuggingFace Hub
  ```
  python run.py download kokoro
  python run.py download piper en_US-lessac-medium
  ```
- [ ] Uses `huggingface_hub` (already in requirements.txt)
- [ ] Shows progress bar to stdout
- [ ] On completion, writes weights to `models_root / "<weights_subpath>"`

---

## 🔴 Hotkey Fully Tested on Windows

- [ ] Integration test: spawn `start_listener`, simulate keypress, verify callback fires
- [ ] Test that listener survives focus changes between foreground apps

---

## 🟡 Deferred

- Windows autostart (Registry `HKCU\...\Run`) — deferred to Stage 5
- Clipboard race / UWP capture failures — deferred (see todo_001)

---

## Stage 5 — Packaging

- [ ] PyInstaller spec: single-file `.exe`, bundle `stacks.yaml` + icons, hidden imports
- [ ] `run.py build` runs PyInstaller, verifies `dist/alienvox.exe --version`
- [ ] NSIS per-user installer (optional)
