#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! AlienVox — single-binary TTS desktop application (Tauri + Win32).
//!
//! Architecture:
//! - **System tray** (Win32): invisible hidden window owns the tray icon.
//!   Right-click opens a context menu per the UI/UX design spec.
//! - **Tauri WebView2**: Balabolka-style UI panel, opened on demand via tray menu.
//! - **SAPI TTS engine**: COM-based SpVoice, initialized lazily on first speak.
//! - **Audio / Capture modules**: platform-specific backends (audio_win.rs, capture_win.rs).

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::Emitter;

/// Bridge: stores the main Tauri window handle so the Win32 tray proc can toggle visibility.
static MAIN_WINDOW: Mutex<Option<tauri::WebviewWindow>> = Mutex::new(None);

/// Bridge: stores the Tauri AppHandle so the tray proc can emit events to the frontend.
static APP_HANDLE: Mutex<Option<tauri::AppHandle>> = Mutex::new(None);
use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM, GetLastError};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, CreatePopupMenu, CreateWindowExW, DefWindowProcW, DestroyMenu,
    DestroyWindow, LoadCursorW, LoadIconW, RegisterClassW,
    ShowWindow, TrackPopupMenuEx, WM_DESTROY, WNDCLASSW, IDI_APPLICATION,
    IDC_ARROW, MF_ENABLED, SW_HIDE, TPM_LEFTALIGN, TPM_RETURNCMD,
    TPM_RIGHTBUTTON, TPM_TOPALIGN, WM_USER,
};
use windows_sys::Win32::UI::WindowsAndMessaging::LoadImageW;
use windows_sys::Win32::UI::Shell::{NIM_ADD, NIF_ICON, NIF_MESSAGE, NIF_TIP, NOTIFYICONDATAW, Shell_NotifyIconW};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::System::Com::{CoInitializeEx, COINIT_APARTMENTTHREADED};
use tauri::Manager;

// ─── Win32 Platform Modules ───────────────────────────────────────────────────
// Platform-specific audio and text-capture backends. Only the module matching
// the target OS is compiled in (cfg-gated).

mod audio {
    #[cfg(target_os = "windows")]
    pub mod audio_win;
    #[cfg(target_os = "macos")]
    mod audio_mac;
}

mod capture {
    #[cfg(target_os = "windows")]
    pub mod capture_win;
    #[cfg(target_os = "macos")]
    mod capture_mac;
}

// Unified, deployment-safe path resolution (ADR-003).  Cross-platform.
mod paths;

// Multi-stack TTS engine abstraction (ADR-004).  Cross-platform.
mod engines;
use engines::TtsEngine;

// ─── System Tray ──────────────────────────────────────────────────────────────
// A hidden Win32 window owns the tray icon.  The UI/UX spec requires a
// right-click context menu with: Speak Selection, Stop, Voice ▸, Settings…,
// About, Quit — in that order.

/// Stores the hidden window handle so we can destroy it on shutdown.
static TRAY_HWND: Mutex<Option<HWND>> = Mutex::new(None);

/// Register a Win32 window class and create a hidden window for tray ownership.
/// `icon_path` is resolved via `paths::tray_icon_path` so it is valid in both dev
/// and deployed builds (ADR-003 §3).
fn create_tray_icon(icon_path: &Path) -> Result<(), String> {
    unsafe {
        // 1. Register a hidden window class whose proc handles tray notifications.
        let class_name = to_wstring("AlienVoxTrayClass");
        let hinstance = GetModuleHandleW(std::ptr::null_mut());
        
        let wc = WNDCLASSW {
            style: 0,
            lpfnWndProc: Some(tray_window_proc),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: hinstance,
            hIcon: 0,
            hCursor: LoadCursorW(0, IDC_ARROW),
            hbrBackground: 0,
            lpszMenuName: std::ptr::null(),
            lpszClassName: class_name.as_ptr(),
        };

        if RegisterClassW(&wc) == 0 {
            return Err(format!("RegisterClassW failed: {}", GetLastError()));
        }

        // 2. Create a hidden (zero-sized, SW_HIDE) window — required by Shell_NotifyIconW.
        let hwnd = CreateWindowExW(
            0,
            class_name.as_ptr(),
            std::ptr::null_mut(),
            0,
            0, 0, 0, 0,
            0,
            0,
            hinstance,
            std::ptr::null_mut(),
        );

        if hwnd == 0 {
            return Err(format!("CreateWindowExW failed: {}", GetLastError()));
        }

        // 3. Load the custom icon (path resolved by paths::tray_icon_path).
        eprintln!("[Tray] Icon path: {}", icon_path.display());
        let wide_icon = to_wstring(icon_path.to_string_lossy().as_ref());
        eprintln!("[Tray] Wide icon len: {}", wide_icon.len());
        let hicon = LoadImageW(
            0,
            wide_icon.as_ptr(),
            1, // IMAGE_ICON
            16,
            16,
            0x10 | 0x20, // LR_LOADFROMFILE | LR_DEFAULTSIZE
        );
        eprintln!("[Tray] LoadImageW returned: {:?} (last error: {})", hicon, GetLastError());

        // 4. Populate NOTIFYICONDATAW and register the icon with the system tray.
        let mut nid = std::mem::zeroed::<NOTIFYICONDATAW>();
        nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
        nid.hWnd = hwnd;
        nid.uID = 1;
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
        nid.uCallbackMessage = WM_USER + 1;
        if hicon != 0 {
            nid.hIcon = hicon as isize;
            println!("[Tray] Custom icon loaded from: {}", icon_path.display());
        } else {
            nid.hIcon = LoadIconW(0, IDI_APPLICATION) as isize;
            eprintln!("[Tray] Failed to load custom icon, using default");
        }
        let tip = to_wstring("AlienVox");
        for i in 0..tip.len().min(127) {
            nid.szTip[i] = tip[i];
        }

        if Shell_NotifyIconW(NIM_ADD, &mut nid) == 0 {
            DestroyWindow(hwnd);
            return Err("Shell_NotifyIconW failed".to_string());
        }

        // 5. Hide the ownership window — only the tray icon should be visible.
        ShowWindow(hwnd, SW_HIDE);

        let mut tray = TRAY_HWND.lock().unwrap();
        *tray = Some(hwnd);
        
        println!("[Tray] Icon created successfully");
        Ok(())
    }
}

/// Destroy the tray icon and clean up the hidden window.
fn destroy_tray_icon() {
    unsafe {
        if let Ok(tray) = TRAY_HWND.lock() {
            if let Some(hwnd) = *tray {
                if hwnd != 0 {
                    let mut nid = std::mem::zeroed::<NOTIFYICONDATAW>();
                    nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
                    nid.hWnd = hwnd;
                    nid.uID = 1;
                    Shell_NotifyIconW(0x0002 /* NIM_DELETE */, &mut nid); // NIM_DELETE = 2
                    DestroyWindow(hwnd);
                }
            }
        }
    }
}

/// Win32 window procedure for the hidden tray-ownership window.
/// Handles WM_DESTROY and tray notification messages (WM_USER + 1).
unsafe extern "system" fn tray_window_proc(_hwnd: HWND, msg: u32, _wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_DESTROY => { 0 }
        msg if msg == WM_USER + 1 => {
            let notification = (lparam & 0xFFFF) as u32;
            match notification {
                // WM_RBUTTONUP — show context menu on right-click.
                0x205 => {
                    show_tray_context_menu(_hwnd);
                    0
                }
                // WM_LBUTTONDBLCLK — toggle main window visibility on double-click.
                0x0203 => {
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
                _ => { 0 }
            }
        }
        _ => DefWindowProcW(_hwnd, msg, _wparam, lparam),
    }
}

/// Show the right-click context menu per the UI/UX design spec:
/// Speak Selection | Stop | --- | Voice ▸ | Settings… | About | Quit
fn show_tray_context_menu(hwnd: HWND) {
    unsafe {
        let menu = CreatePopupMenu();
        if menu == 0 { return; }

        // Separator helper — returns true on success.
        let mut ok = true;

        // Menu items (IDs are arbitrary constants).
        const ID_SPEAK_SEL: u32 = 1001;
        const ID_STOP:      u32 = 1002;
        const ID_VOICE:     u32 = 1003;
        const ID_SETTINGS:  u32 = 1004;
        const ID_ABOUT:     u32 = 1005;
        const ID_QUIT:      u32 = 1006;

        ok &= AppendMenuW(menu, MF_ENABLED, ID_SPEAK_SEL as usize, to_wstring("Speak Selection").as_ptr()) != 0;
        ok &= AppendMenuW(menu, MF_ENABLED, ID_STOP as usize,      to_wstring("Stop").as_ptr())              != 0;
        
        // Separator between Stop and Voice.
        if ok { ok = AppendMenuW(menu, MF_ENABLED | 0x800 /* MF_SEPARATOR */, 0, std::ptr::null()) != 0; }
        
        // Voice submenu placeholder (would enumerate voices in production).
        ok &= AppendMenuW(menu, MF_ENABLED | 0x100 /* MF_POPUP */, ID_VOICE as usize,
                          to_wstring("Voice ▸").as_ptr()) != 0;
        ok &= AppendMenuW(menu, MF_ENABLED, ID_SETTINGS as usize,  to_wstring("Settings…").as_ptr())       != 0;
        ok &= AppendMenuW(menu, MF_ENABLED, ID_ABOUT as usize,     to_wstring("About").as_ptr())           != 0;
        
        // Separator between About and Quit.
        if ok { ok = AppendMenuW(menu, MF_ENABLED | 0x800 /* MF_SEPARATOR */, 0, std::ptr::null()) != 0; }
        
        ok &= AppendMenuW(menu, MF_ENABLED, ID_QUIT as usize,      to_wstring("Quit").as_ptr())            != 0;

        if !ok { DestroyMenu(menu); return; }

        // Position the menu at the cursor.
        #[repr(C)]
        struct POINT { x: i32, y: i32 }
        
        let mut pt = std::mem::zeroed::<POINT>();
        extern "system" { fn GetCursorPos(lppt: *mut POINT) -> i32; }
        GetCursorPos(&mut pt);
        // NOTE: Do NOT call SetForegroundWindow here — it causes Explorer/taskbar flicker.
        let cmd = TrackPopupMenuEx(
            menu,
            TPM_RETURNCMD | TPM_LEFTALIGN | TPM_TOPALIGN | TPM_RIGHTBUTTON,
            pt.x, pt.y,
            hwnd,
            std::ptr::null_mut(),
        ) as u32;
        DestroyMenu(menu);

        // Dispatch the selected command.
        match cmd {
            ID_SPEAK_SEL => println!("[Tray] Speak Selection (stub)"),
            ID_STOP      => println!("[Tray] Stop (stub)"),
            ID_VOICE     => println!("[Tray] Voice submenu (stub)"),
            ID_SETTINGS  => {
                if let Ok(guard) = APP_HANDLE.lock() {
                    if let Some(handle) = &*guard {
                        handle.emit("open-settings", ()).ok();
                    }
                }
            }
            ID_ABOUT     => {
                if let Ok(guard) = APP_HANDLE.lock() {
                    if let Some(handle) = &*guard {
                        handle.emit("open-about", ()).ok();
                    }
                }
            }
            ID_QUIT      => {
                println!("[Tray] Quit requested");
                destroy_tray_icon();
                std::process::exit(0);
            }
            _ => {}
        }
    }
}

/// Convert a Rust &str to a null-terminated UTF-16 vector (wide string).
fn to_wstring(value: &str) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    std::ffi::OsStr::new(value).encode_wide().chain(std::iter::once(0)).collect()
}

// ─── Global TTS Engine State ──────────────────────────────────────────────────
/// Lazy-initialized native SAPI engine.  Created on first call to `speak_text`.
/// The engine owns a dedicated STA thread that holds the `ISpVoice` COM object;
/// see `audio/audio_win.rs`.
static SPEAKER: Mutex<Option<audio::audio_win::NativeAudioEngine>> = Mutex::new(None);
static ML_SPEAKER: Mutex<Option<engines::ml::MlEngine>> = Mutex::new(None);

// ─── Tauri Command Types ──────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Clone, Debug)]
struct VoiceInfo {
    /// Stable SAPI token id (registry path) used to select this voice.
    id: String,
    /// Friendly display name shown in the dropdown.
    name: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct AudioSettings {
    rate: i32,
    pitch: i32,
    volume: u8,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct DocumentState {
    filename: String,
    content: String,
    cursor_line: usize,
    cursor_column: usize,
}

// ─── Tauri Commands ───────────────────────────────────────────────────────────
// These functions are exposed to the frontend via Tauri's IPC bridge.
// The frontend calls them through `invoke()` in JavaScript.

/// Return the list of voices installed on this machine for the given engine tab.
/// `engine` is one of `"sapi5"`, `"speech_platform"`, `"sapi4"`, `"ml"`; unknown or
/// unavailable engines return an empty list.
#[tauri::command]
fn get_voices(app: tauri::AppHandle, engine: String) -> Result<Vec<VoiceInfo>, String> {
    if engine == "ml" {
        let mut guard = ML_SPEAKER.lock().map_err(|e| e.to_string())?;
        if guard.is_none() {
            *guard = Some(engines::ml::MlEngine::new(paths::model_dirs(&app, "ml")));
        }
        let ml = guard.as_ref().unwrap();
        return ml
            .list_voices()
            .map(|voices| {
                voices
                    .into_iter()
                    .map(|v| VoiceInfo { id: v.id, name: v.name })
                    .collect()
            })
            .map_err(|e| e.to_string());
    }

    let mut guard = SPEAKER.lock().map_err(|e| e.to_string())?;
    if guard.is_none() {
        *guard = Some(audio::audio_win::NativeAudioEngine::new()?);
    }
    let speaker = guard.as_ref().unwrap();
    Ok(speaker
        .list_voices(&engine)
        .into_iter()
        .map(|v| VoiceInfo { id: v.id, name: v.name })
        .collect())
}

/// Return current audio settings (defaults).
#[tauri::command]
fn get_audio_settings() -> AudioSettings {
    AudioSettings { rate: 0, pitch: 0, volume: 100 }
}

/// Update audio settings.
#[tauri::command]
fn update_audio_settings(rate: i32, pitch: i32, volume: u8) -> Result<(), String> {
    println!("[TTS Engine] Audio settings updated - Rate: {}, Pitch: {}, Volume: {}", rate, pitch, volume);
    Ok(())
}

/// Create a new empty document.
#[tauri::command]
fn new_document() -> DocumentState {
    DocumentState { filename: "Document1".into(), content: "".into(), cursor_line: 1, cursor_column: 1 }
}

/// Open a text file from disk and return its contents.
#[tauri::command]
fn open_document(path: String) -> Result<DocumentState, String> {
    let file_path = PathBuf::from(&path);
    if !file_path.exists() {
        return Err(format!("File not found: {}", path));
    }
    let content = std::fs::read_to_string(file_path.clone())
        .map_err(|e| format!("Failed to read file: {}", e))?;
    Ok(DocumentState {
        filename: file_path.file_name().unwrap_or_default().to_string_lossy().to_string(),
        content, cursor_line: 1, cursor_column: 1,
    })
}

/// Save document content to disk (or prompt for path if None).
#[tauri::command]
fn save_document(content: String, path: Option<String>) -> Result<(), String> {
    let file_path = match path {
        Some(p) => PathBuf::from(&p),
        None => return Err("No file path provided".to_string()),
    };
    std::fs::write(&file_path, content).map_err(|e| format!("Failed to write file: {}", e))?;
    Ok(())
}

/// Speak the given text through the TTS engine.  Initializes SAPI lazily.
/// `voice` is a SAPI token id (from `get_voices`); empty means the default voice.
#[tauri::command]
fn speak_text(app: tauri::AppHandle, text: String, engine: String, voice: String, rate: i32, pitch: i32, volume: u8) -> Result<(), String> {
    if engine == "ml" {
        let mut guard = ML_SPEAKER.lock().map_err(|e| e.to_string())?;
        if guard.is_none() {
            *guard = Some(engines::ml::MlEngine::new(paths::model_dirs(&app, "ml")));
        }
        let ml = guard.as_ref().unwrap();
        let params = engines::SpeakParams { rate, pitch, volume };
        println!("[ML/AI TTS] Speaking: \"{}\" (voice={}, rate={}, pitch={}, volume={})",
                 text, voice, rate, pitch, volume);
        return ml.speak(&text, &voice, &params).map_err(|e| e.to_string());
    }

    let mut guard = SPEAKER.lock().map_err(|e| e.to_string())?;
    if guard.is_none() {
        *guard = Some(audio::audio_win::NativeAudioEngine::new()?);
    }
    let engine = guard.as_ref().unwrap();
    println!("[TTS Engine] Speaking: \"{}\" (voice={}, rate={}, pitch={}, volume={})",
             text, voice, rate, pitch, volume);
    let voice_id = if voice.trim().is_empty() { None } else { Some(voice) };
    engine.speak(&text, rate, pitch, volume, voice_id)
}

/// Stop any ongoing speech.
#[tauri::command]
fn stop_speaking() -> Result<(), String> {
    let guard = SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.stop(); }
    let guard = ML_SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.stop().map_err(|e| e.to_string())?; }
    Ok(())
}

/// Pause ongoing speech.
#[tauri::command]
fn pause_speaking() -> Result<(), String> {
    let guard = SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.pause(); }
    let guard = ML_SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.pause().map_err(|e| e.to_string())?; }
    Ok(())
}

/// Resume previously paused speech.
#[tauri::command]
fn resume_speaking() -> Result<(), String> {
    let guard = SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.resume(); }
    let guard = ML_SPEAKER.lock().map_err(|e| e.to_string())?;
    if let Some(engine) = guard.as_ref() { engine.resume().map_err(|e| e.to_string())?; }
    Ok(())
}

/// Open the Windows "Speech / voices" settings page so the user can install more
/// voices.  Silent installation isn't possible — voice packages require the
/// Settings/Store flow — so we surface the official page instead.
#[tauri::command]
fn open_voice_settings() -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    std::process::Command::new("cmd")
        .args(["/C", "start", "", "ms-settings:speech"])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map(|_| ())
        .map_err(|e| format!("Failed to open voice settings: {e}"))
}

// ─── Main Entry Point ─────────────────────────────────────────────────────────
/// Application entry point.  Initializes COM, then hands control to Tauri for the
/// WebView2 UI window.  The system tray icon is created in `setup` (below), where
/// the `AppHandle` is available for deployment-safe path resolution (ADR-003).
fn main() {
    // 1. Initialize COM apartment (required before any SAPI calls).
    unsafe { CoInitializeEx(std::ptr::null(), COINIT_APARTMENTTHREADED as u32); }

    // 2. Boot Tauri — manages the Balabolka-style UI window.
    //    Intercept window close to minimize to tray (like the original native app).
    //    Only "Quit" from tray menu should exit the process.
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_voices,
            get_audio_settings,
            update_audio_settings,
            new_document,
            open_document,
            save_document,
            speak_text,
            stop_speaking,
            pause_speaking,
            resume_speaking,
            open_voice_settings,
        ])
        .setup(|app| {
            // Store the main window handle for tray double-click toggle.
            let win = app.get_webview_window("main").unwrap();
            *MAIN_WINDOW.lock().unwrap() = Some(win);
            // Store the AppHandle for tray event emission (Settings, About).
            *APP_HANDLE.lock().unwrap() = Some(app.handle().clone());
            // Create the system tray icon now that path resolution is available.
            let icon = paths::tray_icon_path(app.handle());
            if let Err(e) = create_tray_icon(&icon) {
                eprintln!("[Tray] Failed to create: {}", e);
            }
            Ok(())
        })
        .on_window_event(|_window, event| {
            // Intercept the close button (X) — minimize to tray instead of quitting.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                println!("[Window] Close requested — minimizing to tray");
                _window.hide().ok();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri process");
}
