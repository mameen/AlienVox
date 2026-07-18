//! About window management for AlienVox.
//!
//! Opens a separate Tauri WebviewWindow pointing to `about.html`.

use std::sync::Mutex;

/// Stores the about window handle so it stays alive across calls.
static ABOUT_WINDOW: Mutex<Option<tauri::WebviewWindow>> = Mutex::new(None);

/// Open the About dialog as a separate Tauri window.
#[tauri::command]
pub fn open_about_window(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    println!("[About] Opening About window");

    // Check if an About window already exists; if so, focus and return.
    {
        if let Some(ref win) = *ABOUT_WINDOW.lock().map_err(|e| e.to_string())? {
            println!("[About] About window already exists — focusing");
            win.show().map_err(|e| e.to_string())?;
            win.set_focus().map_err(|e| e.to_string())?;
            return Ok(serde_json::json!({}));
        }
    }

    // Create a new Tauri window pointing to about.html.
    let url = tauri::WebviewUrl::App("about.html".into());
    let win = tauri::WebviewWindowBuilder::new(&app, "about", url)
        .title("About AlienVox")
        .inner_size(680.0, 720.0)
        .resizable(true)
        .center()
        .build()
        .map_err(|e| {
            format!("Failed to create About window: {}", e)
        })?;

    // Keep the window handle alive in a static so it isn't dropped.
    *ABOUT_WINDOW.lock().map_err(|e| e.to_string())? = Some(win.clone());

    // Explicitly show and focus the window.
    win.show().map_err(|e| format!("Failed to show About window: {}", e))?;
    win.set_focus().map_err(|e| format!("Failed to focus About window: {}", e))?;

    println!("[About] About window created and shown successfully");
    Ok(serde_json::json!({}))
}
