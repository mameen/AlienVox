# Issue #001: System Tray Missing Double-Click, Settings, and About Functionality

**Status:** Closed — Superseded  
**Priority:** N/A  
**Created:** 2026-07-13  
**Closed:** 2026-07-18  
**Component:** ~~`gemini_poc/src-tauri/src/main.rs`~~ — Rust/Tauri POC (retired)

---

## Resolution

This issue was specific to the `gemini_poc` Rust + Tauri POC. `gemini_poc` has been retired in favour of `python_app` (Python + PySide6), where `QSystemTrayIcon` handles left-click, right-click, and double-click natively without a custom Win32 window procedure. The architectural gap between a hidden Win32 window and a Tauri `AppHandle` does not exist in the PySide6 implementation.

See `python_app/src/tray.py` — `AlienVoxTray` implements all three interactions via Qt signals.
