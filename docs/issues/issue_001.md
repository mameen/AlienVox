# Issue #001: System Tray Missing Double-Click, Settings, and About Functionality

**Status:** Open  
**Priority:** Medium  
**Created:** 2026-07-13  
**Component:** `gemini_poc/src-tauri/src/main.rs` — Win32 tray integration  

---

## Summary

The system tray icon is created and the right-click context menu works. However:

| Feature | Status | Symptom |
|---|---|---|
| Tray icon visible | ✅ Working | Icon appears in system tray |
| Right-click menu | ✅ Working | Context menu shows all items |
| Quit | ✅ Working | Exits the process cleanly |
| Double-click to show app | ❌ Broken | Nothing happens on double-click |
| Settings… | ❌ Stub | Prints `"[Tray] Settings… (stub — open Tauri window)"` |
| About | ❌ Stub | Prints `"[Tray] About (stub)"` |

---

## Root Cause Analysis

### 1. Double-Click Not Handled

In `tray_window_proc` (line ~170), only `WM_RBUTTONUP` (`0x205`) is handled:

```rust
msg if msg == WM_USER + 1 => {
    let notification = (lparam & 0xFFFF) as u32;
    match notification {
        0x205 => { show_tray_context_menu(_hwnd); 0 }  // only right-click
        _ => { 0 }                                       // double-click silently ignored
    }
}
```

The `WM_LBUTTONDBLCLK` (`0x0203`) notification is never matched, so double-clicks are dropped.

### 2. Settings / About Are Print-Only Stubs

In `show_tray_context_menu` (lines 243–244):

```rust
ID_SETTINGS => println!("[Tray] Settings… (stub — open Tauri window)"),
ID_ABOUT    => println!("[Tray] About (stub)"),
```

These commands only log to stdout. They do not:
- Open a secondary window
- Emit events to the frontend
- Interact with the Tauri app in any way

### 3. Architectural Gap: Tray Proc ↔ Tauri Bridge

The tray window procedure (`tray_window_proc`) runs on a **hidden Win32 window** that exists before Tauri boots. The Tauri app manages its own event loop and owns the main WebView2 window. There is no bridge between them.

Specifically:
- The tray proc has no reference to `tauri::Window` to call `.show()` / `.hide()`
- No mechanism exists for the tray proc to send commands/events to the Tauri app
- The Tauri app does not expose a way for external Win32 code to interact with it

---

## Required Fixes

### Fix 1: Double-Click Toggle

**Approach:** Store the main Tauri window in a `static` after boot, then toggle visibility from the tray proc.

```rust
// Add static storage (thread-safe):
use std::sync::Arc;
static MAIN_WINDOW: Mutex<Option<tauri::Window>> = Mutex::new(None);

// In main(), after Builder setup:
.on_window_event(|window, event| { ... })
.setup(|app| {
    let win = app.get_webview_window("main").unwrap();
    *MAIN_WINDOW.lock().unwrap() = Some(win);
    Ok(())
})

// In tray_window_proc, add WM_LBUTTONDBLCLK handler:
0x203 => {  // WM_LBUTTONDBLCLK
    if let Ok(w) = MAIN_WINDOW.lock() {
        if let Some(ref win) = *w {
            if win.is_visible().unwrap_or(false) {
                win.hide().ok();
            } else {
                win.show().ok();
                win.set_focus().ok();
            }
        }
    }
    0
}
```

### Fix 2: Settings — Emit Event to Frontend

**Approach:** Use `app.emit()` from the tray proc. The tray proc needs access to the Tauri `AppHandle`.

```rust
// Store AppHandle in a static:
static APP_HANDLE: Mutex<Option<tauri::AppHandle>> = Mutex::new(None);

// In main(), setup phase:
.setup(|app| {
    *APP_HANDLE.lock().unwrap() = Some(app.handle());
    Ok(())
})

// In show_tray_context_menu, ID_SETTINGS handler:
ID_SETTINGS => {
    if let Ok(Some(handle)) = APP_HANDLE.lock() {
        handle.emit("open-settings", ()).ok();
    }
}
```

### Fix 3: About — Emit Event or Open Dialog Window

**Approach A (preferred):** Emit event to frontend for the UI to render an About dialog.

```rust
ID_ABOUT => {
    if let Ok(Some(handle)) = APP_HANDLE.lock() {
        handle.emit("open-about", ()).ok();
    }
}
```

**Approach B:** Open a separate Tauri window as a modal About dialog (requires `tauri::Window` builder).

---

## Files to Modify

| File | Changes |
|---|---|
| `gemini_poc/src-tauri/src/main.rs` | Add `MAIN_WINDOW` + `APP_HANDLE` statics, update `tray_window_proc`, update `show_tray_context_menu`, add `.setup()` to Tauri Builder |

## Files to Modify (Frontend)

| File | Changes |
|---|---|
| `gemini_poc/frontend/` (or `src/`) | Add event listeners for `open-settings` and `open-about` events |

## Dependencies

- No new Rust crates needed — uses existing `tauri::AppHandle`, `tauri::Window`, and `std::sync::Mutex`
- Frontend needs Tauri event listener API (`window.addEventListener('tauri', ...)` or `invoke`)
