# AlienVox python_app — Known Remaining Tasks

**Last updated:** 2026-07-18 (Stage 2 partial + main window)  
**Status legend:** 🔴 Not started · 🟡 Deferred · 🟠 In progress / partial · 🟢 Done

---

## Project context (read this before working on any task)

AlienVox is a Windows "Speak Selection" utility — highlight any text, press the global hotkey
(`Ctrl+Esc` by default), and the selected text is spoken aloud. It lives in the system tray with
no persistent main window during normal operation.

**Stack:**  Python 3.11 · PySide6 (Qt6) · pywin32 · pynput  
**Repo layout (relevant paths):**

```
tts/python_app/
  run.py                    # task runner: python run.py [app|build|test|lint|cov|perf|all]
  stacks.yaml               # bundled config: all stacks, models, voices, controls
  src/
    main.py                 # entry point — run with: python -m src.main
    tray.py                 # QSystemTrayIcon + context menu
    main_window.py          # Balabolka-style testing / settings window (opens on startup)
    about.py                # About dialog
    preferences.py          # DEAD CODE — old tabbed dialog, no longer opened
    capture.py              # Text selection capture (WM_COPY → Ctrl+C fallback)
    hotkey.py               # pynput GlobalHotKeys listener
    telemetry.py            # Dual-sink telemetry: stderr + JSONL file
    config.py               # Four-layer config: defaults → stacks.yaml → user.yaml
    engines/
      base.py               # TtsEngine ABC, Voice dataclass, SpeakParams dataclass
      registry.py           # Reads stacks.yaml, checks weights on disk → StackInfo list
      sapi_win.py           # Windows SAPI5 engine via pywin32 COM (Windows only)
  tests/
    conftest.py             # Shared fixtures: stacks_yaml, models_root, user_yaml
    fixtures/stacks.yaml    # Test fixture mirroring production stacks.yaml
    test_config.py          # 19 tests — config resolution and YAML helpers
    test_telemetry.py       # 10 tests — telemetry emit, session/request IDs, privacy
    test_registry.py        # 9 tests — stack availability, weight detection, voice list
    test_capture.py         # 8 tests — clipboard round-trips (Windows only, skip otherwise)
    test_sapi.py            # 11 tests — SAPI voice enum, speak_to_wav, stop/pause (Windows only)
    test_perf.py            # 9 benchmarks — config/registry/telemetry latency thresholds
```

**Key design rules:**
- Single executable, no subprocess calls to Python interpreter at runtime.
- `stacks.yaml` is bundled next to the exe (prod) or next to `setup.py` (dev) — no filesystem scanning.
- Telemetry: `ALIENVOX_TELEMETRY <json>` to stderr **and** append to `%LOCALAPPDATA%/com.alientech.alienvox/telemetry.jsonl`. **Never log source text.**
- No mocking internal code in tests — stub only at OS/hardware boundary (COM objects, audio devices).
- 80% line-coverage floor enforced by `--cov-fail-under=80` (UI and Windows-only modules excluded from measurement).
- Voice IDs for SAPI5 are registry token paths (e.g. `HKEY_LOCAL_MACHINE\...\TTS_MS_EN-US_DAVID_11.0`), not volatile integer indices.

---

## Stage 2 — Windows APIs (current)

### Text capture (`src/capture.py`)

Implemented and functional:
- 🟢 Tier 1: `WM_COPY` to focused control via `AttachThreadInput` + `SendMessage`
- 🟢 Tier 2: `keybd_event` Ctrl+C fallback with clipboard save/restore
- 🟢 `_read_clipboard()` / `_write_clipboard()` helpers (tested)
- 🟢 8 tests in `test_capture.py` covering clipboard round-trips (Windows only, skip otherwise)

**Deferred items** — do not work on these until Stage 2 core is otherwise stable:

The following are **deferred** — do not work on these until Stage 2 core is otherwise stable:

- 🟡 **Clipboard race** *(deferred)*: No retry loop — if the target app takes >40 ms to update the
  clipboard after WM_COPY, capture silently returns empty. Fix: poll the clipboard in a short loop
  (e.g. 5 × 10 ms, break early when clipboard content changes from the saved value).
- 🟡 **UWP / sandboxed apps** *(deferred)*: WM_COPY and Ctrl+C fail silently in Store apps
  (modern Edge, Win11 Notepad). Fix: detect restricted processes via
  `GetWindowThreadProcessId` + `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and show a tray
  balloon notification ("Selection capture not supported in this app") instead of silent empty result.
- 🟡 **Test coverage** *(deferred)*: `test_capture.py` covers clipboard helpers only. Add integration
  test using `pywinauto` or `win32api` to open Notepad, type + select text, and verify
  `get_selected_text()` returns it.

### SAPI5 engine (`src/engines/sapi_win.py`)

- 🟢 Stable voice IDs (registry token path, not integer index)
- 🟢 `speak(text, voice_id, params)` — async (`SVSFlagsAsync`)
- 🟢 `speak_sync(text, voice_id, params)` — blocking
- 🟢 `speak_to_wav(text, voice_id, params, out_path)` — renders to WAV, no audio hardware needed
- 🟢 `stop()` / `pause()` / `resume()`
- 🟢 Thread lock on all COM calls
- 🟢 27 tests in `test_sapi.py` (Windows only, skip otherwise)
  - Voice enum: 5 tests (count, IDs, names, registry paths, uniqueness)
  - speak_to_wav: 4 tests (creates file, valid WAV, rate diff, voice selection)
  - stop/pause/resume: 3 tests
  - Thread safety: 2 tests (concurrent speak, concurrent stop+speakspeak)
  - Error handling: 4 tests (bad voice_id, empty text, bad voice wav, non-string text)
  - SSML/pitch: 6 tests (escape XML x3, build_ssml plain/pitch/escaped, speak with pitch)
  - WaitUntilDone: 3 tests (timeout returns bool, no block, completes with generous timeout)
- 🟢 **WaitUntilDone timeout**: Replaced `WaitUntilDone(-1)` with `engine.wait_until_done(30_000)` + `tts.error` telemetry + `tray.set_error()` on failure. Added `wait_until_done()` wrapper method to SapiEngine.
- 🟢 **Main window Play button speaks editor text**: `speak(text: str | None = None)` now accepts optional text. When called from main window ▶, passes editor content directly (bypasses capture). Tray menu calls `speak_async()` with no arg → captures selection.
- 🟢 **Voice selection persistence**: Voice dropdown `currentIndexChanged` → `_on_voice_changed()` → `save_user_override({"voice": vid})` + refreshes tray checkmarks via `on_voice_changed` callback.
- 🟢 **Slider persistence**: Each slider `valueChanged` → `_on_slider_debounced()` → QTimer 350ms single-shot → `_save_pending_sliders()` → `save_user_override(patch)`.
- 🟢 **Pitch support via SAPI XML**: Added `_escape_xml()` and `_build_ssml()` to wrap text in `<pitch absmiddle="N"/>` SSML when pitch ≠ 0. Applied in both `speak()` and `speak_to_wav()`.
- 🟢 **Playback completion telemetry**: Emits `tts.first_audio` (latency to SAPI submit) and `tts.playback_end` (status: "complete"/"timeout") matching Rust POC pattern.
  Add a debounced `QTimer` (~350 ms) on slider `valueChanged` to call `save_user_override`.

---

## Stage 3 — ML Inference (not started)

> All ML engines must run **in-process** — no subprocess, no external runtime calls.
> Use `speak_to_wav()` for offline tests so CI does not need audio hardware.

### Shared audio playback (`src/audio_win.py`)
- 🔴 Create `src/audio_win.py` with a single public function:
  `play_wav_bytes(data: bytes, sample_rate: int, channels: int) -> None`
  Use `sounddevice.play()` (cross-platform) as the first implementation.
  Playback must be interruptible: expose `stop_playback() -> None`.
- 🔴 Wire into ML engine `speak()` path: generate audio → `play_wav_bytes()`.

### Kokoro-82M (`src/engines/kokoro_engine.py`)
- 🔴 Implement `TtsEngine` using the `kokoro` Python package.
  `list_voices()` returns voices from `stacks.yaml` `ml/kokoro` entry.
  `speak()` → generate PCM → `audio_win.play_wav_bytes()`.
  `speak_to_wav()` → write raw PCM as WAV using `wave` stdlib.
- 🔴 Weight detection: check `models_root / "ml/kokoro"` exists (done by registry). If missing,
  show an "Install model" prompt in the main window status bar.
- 🔴 Wire into `main.py` `_load_engine()`: `elif engine_id == "ml" and model_id == "kokoro"`.

### Piper ONNX (`src/engines/piper_engine.py`)
- 🔴 Implement `TtsEngine` using `piper-tts` (in-process ONNX, no subprocess).
- 🔴 Voice install: each Piper voice is a separate ONNX file. `stacks.yaml` lists
  `weights_subpath: ml/piper/<voice_id>`. Install each voice independently.
- 🔴 Expose Piper-specific controls in main window:
  `noise_scale`, `noise_w`, `sentence_silence` — defined in `stacks.yaml` `ml/piper/controls`.
  Add a "Piper Controls" collapsible strip below the main sliders when Piper is the active model
  (see Rust `#model-controls-piper` in `gemini_poc/frontend/index.html` for the reference design).

### Dia (`src/engines/dia_engine.py`)
- 🔴 Implement `TtsEngine` using the `dia` package (Apache 2.0, GPU-oriented).
- 🔴 GPU check: if `torch.cuda.is_available()` is False, show a warning in the main window model
  dropdown tooltip and disable the model.

### VibeVoice-Realtime-0.5B (`src/engines/vibevoice_engine.py`)
- 🔴 Implement `TtsEngine` using `transformers` + `torch` (MIT, research stage).
- 🔴 VibeVoice produces streaming audio chunks. Pipe each chunk to `sounddevice` for real-time
  playback rather than buffering the full utterance.

---

## Stage 4 — Main Window Polish

Reference design: `gemini_poc/frontend/index.html` (Rust/Tauri version — full HTML/CSS/JS).

### Currently done
- 🟢 Toolbar: ▶ (green, `#22c55e`) / ⏸ (gray, `#6b7280`) / ⏹ (red, `#ef4444`) painted as
  `QIcon` via `QPainter` (not emoji — emoji ignores CSS color in Qt); file buttons use text emoji.
- 🟢 Engine tabs: SAPI4 placeholder (disabled) + one tab per stack from `stacks.yaml`.
- 🟢 Voice controls bar: model dropdown + voice dropdown + TTL spinbox + status label + Install button.
- 🟢 Audio sliders: Rate / Pitch / Volume with `applies: false` → greyed out.
- 🟢 Text editor: `QPlainTextEdit`, Consolas 11pt, char count in status bar.
- 🟢 Opens on app startup; double-click tray icon toggles show/hide.
- 🟢 Appears in Windows taskbar (`Qt.WindowType.Window` flag).
- 🟢 About dialog: logo + version + scrollable sections + footer — matches Rust design.
- 🟢 Task runner `run.py`: `app` / `build` / `lint` / `test` / `cov` / `perf` / `all`.
  `app` runs `python -m src.main` (module mode, fixes relative-import error).
- 🟢 `.gitignore` covers test artifacts: `.coverage`, `htmlcov/`, `.pytest_cache/`, `perf_results*.json`, `*.jsonl`.

### Remaining
- 🔴 **Piper extra controls strip**: below the main sliders, show `noise_scale`, `noise_w`,
  `sentence_silence` sliders when the Piper model is active. See `stacks.yaml` `ml/piper/controls`
  for min/max/default. Mirror Rust `#model-controls-piper` section.
- 🔴 **Model availability LEDs**: prepend `🟢` (weights found) or `⚪` (not installed) to each
  model name in the model dropdown. Call `registry.available_stacks()` at startup to get
  `ModelInfo.available` per model. Update when install completes.
- 🔴 **Install Model dialog**: "Install Model" button opens a `QDialog` with:
  model name, download size (placeholder), `QProgressBar`, Cancel button.
  Runs download in a `threading.Thread`; emits progress via Qt signal to update the bar.
- 🔴 **Export to WAV** (`🎵` button): open `QFileDialog.getSaveFileName()` for `.wav`, then call
  `engine.speak_to_wav(text, voice_id, params, path)` in a thread.
- 🔴 **Open text file** (`📂` button): `QFileDialog.getOpenFileName()` for `.txt`; read and set
  editor content.
- 🔴 **Save text file** (`💾` button): `QFileDialog.getSaveFileName()` for `.txt`; write editor
  content.
- 🔴 **Cursor position in status bar**: `Line: N, Column: N` updated on every cursor move.
  Connect `QPlainTextEdit.cursorPositionChanged` to a slot that computes line/col from
  `textCursor().blockNumber()` and `textCursor().columnNumber()`.
- 🔴 **Window geometry persistence**: on close, save `window.geometry()` to `user.yaml`
  (`window_x`, `window_y`, `window_w`, `window_h`). On open, restore via `setGeometry()`.
- 🔴 **Voice dropdown writes to `user.yaml`**: see Stage 2 SAPI5 item above (same fix, apply to
  all tabs not just SAPI5).
- 🔴 **Slider debounce writes to `user.yaml`**: see Stage 2 SAPI5 item above.

### Preferences / Global Settings
- 🔴 **`preferences.py` is dead code** — the old tabbed dialog is no longer opened. Options:
  (a) delete it and add a "Global" tab to the main window containing hotkey + startup-with-Windows
  toggle; or (b) repurpose it as a modal opened from a Settings… menu item in the toolbar.
- 🔴 **Hotkey rebinding**: currently hardcoded as `<ctrl>+<esc>` in `DEFAULTS` in `config.py`.
  Wire a `QKeySequenceEdit` or plain `QLineEdit` (pynput format) in the Global tab.
- 🔴 **"Start with Windows" toggle**: write/delete
  `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\AlienVox` registry key.

---

## Stage 5 — Packaging

- 🔴 **PyInstaller spec** (`python_app/alienvox.spec`): single-file `.exe`, bundle `stacks.yaml`
  and `src/resources/icons/`, set `--icon=src/resources/icons/icon.ico`.
  Add `--hidden-import win32com.client` and `--hidden-import pynput.keyboard`.
- 🔴 **`run.py build` enhancement**: after py_compile syntax check, also run PyInstaller and verify
  the output `dist/alienvox.exe` exists and exits 0 when called with `--version`.
- 🔴 **Installer** (optional): NSIS or WiX Toolset for a per-user `setup.exe`.

---

## Testing gaps

- 🔴 **Windows CI**: `test_sapi.py` and `test_capture.py` are skipped on non-Windows. Add a
  GitHub Actions `windows-latest` job that runs the full test suite.
- 🔴 **UI tests**: `main_window.py`, `tray.py`, `about.py` need `pytest-qt` integration tests
  (`QApplication` fixture). Deferred until `PySide6` is confirmed installed in CI.
- 🔴 **Perf thresholds**: `test_perf.py` uses 10× headroom values. Measure baseline on target
  hardware and tighten to ~3× headroom.
- 🔴 **Coverage omit shrinkage**: as each UI module gets `pytest-qt` tests, remove it from the
  `omit` list in `pyproject.toml` and ensure the 80% floor still holds.

---

## Known bugs / UX rough edges

- 🔴 **`_speak_lock` release guard** (`src/main.py`): if `_speak_lock.release()` is called when
  already released (e.g. double-stop), a `RuntimeError` is raised. Wrap in `try/except RuntimeError`.
- 🔴 **Empty-text speak notification**: if no text is selected and the hotkey fires, `speak()` sets
  idle silently. Show a tray balloon: `tray._tray.showMessage("AlienVox", "No text selected", ...)`.
- 🔴 **SAPI COM init failure**: if `SapiEngine.__init__()` raises (no SAPI, no voices installed),
  `_load_engine()` in `main.py` returns `None` silently. Log a `tts.error` telemetry event and
  show a status message in the main window.
- 🔴 **SAPI5 voice bar placeholder**: `update_sapi_voices()` is only called when the SAPI engine
  initialises successfully. If it fails, the voice dropdown still shows the placeholder text
  "(populated from OS at runtime)". Replace with an error message in that case.
- 🔴 **Single-click vs. context menu timing**: `QSystemTrayIcon Trigger` fires on the first mouse
  button press. On some Windows versions this races with the right-click context menu. Consider
  making single-click show/hide the main window (less surprising) and keeping speak on the hotkey
  and the "Speak Selection" menu item only.
