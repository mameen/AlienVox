# TODO #001: AlienVox — Main Window & UI

**Status:** Open  
**Updated:** 2026-07-20  
**Scope:** `src/main_window.py`, `src/about.py`, `src/tray.py`, `src/preferences.py`

Reference design: `gemini_poc/frontend/index.html` (Rust/Tauri — full HTML/CSS/JS)

---

## Done

- [x] Balabolka-style main window: engine tabs, sliders, text canvas, playback toolbar
- [x] Toolbar: ▶ / ⏸ / ⏹ painted as `QIcon` via `QPainter` (exact Rust colors)
- [x] Engine tabs: one tab per stack from `stacks.yaml`
- [x] Voice bar: model dropdown + voice dropdown + TTL + status + Install button
- [x] Audio sliders: Rate / Pitch / Volume; greyed out when `applies: false`
- [x] Text editor: `QPlainTextEdit`, Consolas 11pt, char count in status bar
- [x] Opens on startup; double-click tray toggles show/hide; appears in taskbar
- [x] About dialog: logo + version + scrollable sections — matches Rust design
- [x] About [X] button fixed (explicit window flags)
- [x] About button added to toolbar (right-aligned, logo icon)

---

## Open

### Voice Dropdown Not Populated (SAPI5 tab)

`_build_voice_bar` adds placeholder `"(populated from OS at runtime)"` for `sapi5`
but `MainWindow` never receives the live voice list from the engine.

- [ ] Accept `live_voices: list[dict] | None` in `MainWindow.__init__`
- [ ] Call `_populate_sapi_voices(voices)` during init if `live_voices` is provided
- [ ] Also expose `update_voices(stack_id, voices)` so `main.py` can refresh after engine loads
- [ ] Set current index to match `cfg.get("voice", "")` after populating

### Speech Platform Tab Missing

The Rust UI has a **SAPI 4** placeholder tab + **SAPI 5** + **Speech Platform** + **ML/AI**.
Python `stacks.yaml` only has `sapi5` and `ml`. See `todo_002.md` for the engine work.

- [ ] Add `speech_platform` tab to main window once `stacks.yaml` has the entry
- [ ] Show greyed out / "Not installed" when Speech Platform runtime is absent

### Piper Extra Controls Strip

When Piper model is active, show `noise_scale`, `noise_w`, `sentence_silence` sliders
below the main slider strip (see `stacks.yaml` `ml/piper/controls` for min/max/default).
Mirrors Rust `#model-controls-piper` section.

- [ ] Collapsible strip below main sliders, visible only when active model == piper
- [ ] Values saved to `user.yaml` via debounced slider → `save_user_override`

### Model Availability LEDs

- [ ] Prepend `🟢` / `⚪` to each model name in model dropdown
- [ ] Read `ModelInfo.available` from `registry.available_stacks()` at startup
- [ ] Update when Install completes

### Install Model Dialog

- [ ] "Install Model" button → `QDialog` with model name, download size, `QProgressBar`, Cancel
- [ ] Download in `threading.Thread`; emit progress via Qt signal

### Other Polish

- [ ] Export WAV (`🎵` button): `QFileDialog` → `engine.speak_to_wav()`
- [ ] Open text file (`📂`): `QFileDialog` → set editor content
- [ ] Save text file (`💾`): `QFileDialog` → write editor content
- [ ] Cursor position in status bar: `Line: N, Col: N`
- [ ] Window geometry persistence: save/restore `window_x/y/w/h` in `user.yaml`
- [ ] Preferences / hotkey rebinding (Global tab or modal)
- [ ] "Start with Windows" toggle → Registry `HKCU\...\Run`
- [ ] Delete dead code `src/preferences.py`

### Known UX Bugs

- [ ] `_speak_lock.release()` when already released → `RuntimeError`; wrap in `try/except`
- [ ] Empty-text hotkey fires silently; show tray balloon "No text selected"
- [ ] SAPI init failure leaves placeholder in voice dropdown; show error message instead
- [ ] **Voice selection doesn't apply**: `on_voice_changed` saves to `user.yaml` but doesn't update in-memory `cfg`; next `speak()` still reads stale `cfg.get("voice", "")` → always uses the original voice
- [ ] **Speech Platform tab shows "(loading voices…)"**: `_ensure_main_window()` only enumerates voices for `active_stack`, so non-active stacks (e.g. `speech_platform` when `sapi5` is active) never get their voice list populated
