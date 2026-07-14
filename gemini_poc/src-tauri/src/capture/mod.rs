#[cfg(target_os = "windows")]
mod capture_win;

#[cfg(target_os = "macos")]
mod capture_mac;
