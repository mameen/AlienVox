# TODO #002: AlienVox — Engine Functionality

**Status:** Open  
**Updated:** 2026-07-19  
**Scope:** `src/engines/`, `src/main.py`, `stacks.yaml`, `src/audio_win.py`

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

---

## 🔴 SAPI5 — Voice Dropdown Not Wired

`main.py` collects `live_voices` but never passes it to `MainWindow`.
The SAPI5 tab always shows `"(populated from OS at runtime)"`.

- [ ] Pass `live_voices` to `MainWindow` constructor (or call `update_voices` after creation)
- [ ] Set selected voice to match `cfg.get("voice", "")` on startup
- [ ] On voice change: `save_user_override({"voice": vid})` + refresh tray checkmarks

---

## 🔴 Speech Platform Stack (Microsoft Speech Server v11)

Rust `audio_win.rs` has a third hive:
```
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0\Voices
```
This is the **Microsoft Speech Platform** runtime — separate from SAPI5 and OneCore.
It has higher-quality voices (e.g. Microsoft Helen, Hazel, David in Speech Platform quality).
The Rust UI shows it as a separate tab between SAPI5 and ML/AI.

- [ ] Add `speech_platform` entry to `stacks.yaml`:
  ```yaml
  - id: speech_platform
    name: Speech Platform
    platform: win32
    weights_subpath: ""
    controls:
      rate:   { min: -10, max: 10,  default: 0,   applies: true }
      pitch:  { min: -10, max: 10,  default: 0,   applies: true }
      volume: { min: 0,   max: 100, default: 100, applies: true }
  ```
- [ ] Add `speech_platform` handling to `registry.py`:
  Check `HKLM\SOFTWARE\Microsoft\Speech Server\v11.0\Voices` registry key exists;
  mark available only if at least one voice token is present.
- [ ] Add `speech_platform` to `_VOICE_CATEGORIES` in `sapi_win.py` (or a separate hive
  list per stack). `_load_engine("speech_platform")` can reuse `SapiEngine` with a
  different category list.
- [ ] Update `_load_engine()` in `main.py` to handle `speech_platform` stack.

---

## 🔴 ML Stack — Shared Audio Playback

All ML engines produce raw PCM/WAV bytes. They need a shared playback layer.

- [ ] Create `src/audio_win.py`:
  ```python
  def play_wav_bytes(data: bytes, sample_rate: int, channels: int) -> None
  def stop_playback() -> None
  ```
  Use `sounddevice.play()` (already in `requirements.txt`). Playback interruptible.
- [ ] Wire `stop_playback()` into `engine.stop()` for all ML engines.

---

## 🔴 Kokoro-82M (`src/engines/kokoro_engine.py`)

- [ ] Implement `TtsEngine` using the `kokoro` Python package (already in requirements.txt)
- [ ] `list_voices()` → returns voices from `stacks.yaml` `ml/kokoro` entry
- [ ] `speak(text, voice_id, params)` → `kokoro.generate()` → `audio_win.play_wav_bytes()`
- [ ] `speak_to_wav(text, voice_id, params, path)` → write PCM as WAV via `wave` stdlib
- [ ] Weight detection: registry checks `models_root / "ml/kokoro"` exists
- [ ] Wire into `_load_engine()`: `engine_id == "ml" and model_id == "kokoro"`
- [ ] `wait_until_done()`: wait on playback thread event

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
