#[cfg(target_os = "windows")]
#[path = "main_win.rs"]
mod implementation;

#[cfg(target_os = "macos")]
#[path = "main_mac.rs"]
mod implementation;

pub fn run() -> ! {
    implementation::run()
}
