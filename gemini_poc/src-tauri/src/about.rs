//! About window management for AlienVox.
//!
//! The About window is declared statically in `tauri.conf.json` with label `"about"`
//! and starts hidden (`"visible": false`).  These commands toggle visibility.

use tauri::Manager;

/// Show the About dialog (it starts hidden via tauri.conf.json).
#[tauri::command]
pub fn open_about_window(app: tauri::AppHandle) -> Result<(), String> {
    let win = app
        .get_webview_window("about")
        .ok_or_else(|| "About window not found in tauri.conf.json".to_string())?;
    win.show()
        .map_err(|e| format!("Failed to show About window: {}", e))?;
    win.set_focus()
        .map_err(|e| format!("Failed to focus About window: {}", e))?;
    Ok(())
}

/// Hide the About dialog.  The window stays alive so it can be shown again.
#[tauri::command]
pub fn close_about_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("about") {
        win.hide()
            .map_err(|e| format!("Failed to hide About window: {}", e))?;
    }
    Ok(())
}
