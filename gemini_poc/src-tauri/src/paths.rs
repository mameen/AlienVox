//! Unified, deployment-safe path resolution (ADR-003).
//!
//! Every on-disk asset — the tray icon, config, and neural `.models` — resolves
//! through this module so behaviour is identical in `cargo tauri dev` and in a
//! shipped binary.  It relies on Tauri's runtime path API rather than compile-time
//! paths; the sole compile-time path (`CARGO_MANIFEST_DIR`) is confined to a
//! **debug-only** developer override that is never present in a release build.
#![allow(dead_code)]

use std::path::PathBuf;

use tauri::{AppHandle, Manager};

/// Writable per-user data root: `%LOCALAPPDATA%\<identifier>\`.
/// This is where downloaded models and user config are written (ADR-003 §1, §4·1).
pub fn app_data_root(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_local_data_dir().ok()
}

/// Read-only bundled resources root, next to the installed executable (ADR-003 §4·2).
pub fn resource_root(app: &AppHandle) -> Option<PathBuf> {
    app.path().resource_dir().ok()
}

/// The project-local `.models` root, for the developer iteration loop only.
/// Debug builds resolve `<repo>/gemini_poc/.models`; release builds return `None`.
fn dev_models_root() -> Option<PathBuf> {
    #[cfg(debug_assertions)]
    {
        // CARGO_MANIFEST_DIR = <repo>/gemini_poc/src-tauri → parent is gemini_poc.
        Some(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join(".models"),
        )
    }
    #[cfg(not(debug_assertions))]
    {
        None
    }
}

/// Candidate `.models/<stack>` directories in ADR-003 §4 priority order:
///   1. Writable local app data  (primary — downloaded models)
///   2. Bundled app resources     (only if we pre-ship models)
///   3. Local dev override        (debug builds only)
///
/// Callers scan each existing directory and merge results; missing dirs are skipped.
pub fn model_dirs(app: &AppHandle, stack: &str) -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Some(root) = app_data_root(app) {
        dirs.push(root.join(".models").join(stack));
    }
    if let Some(root) = resource_root(app) {
        dirs.push(root.join(".models").join(stack));
    }
    if let Some(root) = dev_models_root() {
        dirs.push(root.join(stack));
    }
    dirs
}

/// Resolve the tray icon (`icons/icon.ico`), preferring the bundled resource in a
/// deployed build and falling back to the project `icons/` dir during development.
/// Replaces the former `env!("CARGO_MANIFEST_DIR")` lookup, which only existed on
/// the build machine and would fail on any other computer (ADR-003 §3).
pub fn tray_icon_path(app: &AppHandle) -> PathBuf {
    // 1. Deployed: <resource_dir>/icons/icon.ico.
    if let Some(root) = resource_root(app) {
        let p = root.join("icons").join("icon.ico");
        if p.exists() {
            return p;
        }
    }
    // 2. Dev: project src-tauri/icons/icon.ico.
    #[cfg(debug_assertions)]
    {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("icons")
            .join("icon.ico");
        if dev.exists() {
            return dev;
        }
    }
    // 3. Last resort: alongside the executable.
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|dir| dir.join("icons").join("icon.ico")))
        .unwrap_or_else(|| PathBuf::from("icons/icon.ico"))
}
