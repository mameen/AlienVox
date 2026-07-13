use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};
use windows_sys::Win32::Foundation::{HWND, HINSTANCE, LPARAM, LRESULT, POINT, WPARAM};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::Shell::{
    NIM_ADD, NIM_DELETE, NIF_ICON, NIF_MESSAGE, NIF_TIP, NOTIFYICONDATAW, Shell_NotifyIconW,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, BN_CLICKED, BS_DEFPUSHBUTTON, CreatePopupMenu, CreateWindowExW, DefWindowProcW,
    DestroyMenu, DestroyWindow, DispatchMessageW, GetCursorPos, GetMessageW, LoadCursorW,
    LoadIconW, LoadImageW, PostQuitMessage, RegisterClassW, SendMessageW, SetForegroundWindow,
    SetWindowTextW, ShowWindow, TrackPopupMenuEx, TranslateMessage, CW_USEDEFAULT, HMENU,
    IDC_ARROW, IDI_APPLICATION, ICON_BIG, LR_LOADFROMFILE, MF_ENABLED, MF_STRING, MSG, SW_HIDE,
    SW_SHOW, TPM_LEFTALIGN, TPM_RETURNCMD, TPM_RIGHTBUTTON, TPM_TOPALIGN, UnregisterClassW,
    WM_CLOSE, WM_COMMAND, WM_DESTROY, WM_SETICON, WM_USER, WNDCLASSW, WS_CHILD,
    WS_OVERLAPPEDWINDOW, WS_VISIBLE,
};

static STATE: OnceLock<Mutex<TrayState>> = OnceLock::new();

#[derive(Default)]
struct TrayState {
    tray_hwnd: HWND,
    main_hwnd: HWND,
    preferences_hwnd: HWND,
    tray_class_name: Vec<u16>,
    main_class_name: Vec<u16>,
    preferences_class_name: Vec<u16>,
    quitting: bool,
}

fn state() -> &'static Mutex<TrayState> {
    STATE.get_or_init(|| Mutex::new(TrayState::default()))
}

pub fn run() -> ! {
    println!("AlienVox tray application starting...");

    let tray = TrayHandle::new().unwrap_or_else(|err| {
        eprintln!("Failed to create tray icon: {}", err);
        std::process::exit(1);
    });

    println!("AlienVox tray icon created.");
    tray.run();
}

struct TrayHandle {
    tray_hwnd: HWND,
    main_hwnd: HWND,
    tray_class_name: Vec<u16>,
    main_class_name: Vec<u16>,
}

impl TrayHandle {
    fn new() -> Result<Self, String> {
        let tray_class_name = to_wstring("AlienVoxTrayWindow");
        let main_class_name = to_wstring("AlienVoxMainWindow");
        let hinstance = unsafe { GetModuleHandleW(std::ptr::null()) as HINSTANCE };

        let main_hwnd = create_main_window(&main_class_name, hinstance)?;
        let tray_hwnd = create_tray_window(&tray_class_name, hinstance)?;

        let mut state_lock = state().lock().unwrap();
        state_lock.tray_hwnd = tray_hwnd;
        state_lock.main_hwnd = main_hwnd;
        state_lock.tray_class_name = tray_class_name.clone();
        state_lock.main_class_name = main_class_name.clone();
        drop(state_lock);

        let icon = load_icon(&app_icon_path());
        let mut nid = unsafe { std::mem::zeroed::<NOTIFYICONDATAW>() };
        nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
        nid.hWnd = tray_hwnd;
        nid.uID = 1;
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        nid.uCallbackMessage = WM_USER + 1;
        nid.hIcon = icon;
        let tip = to_wstring("AlienVox");
        nid.szTip[..tip.len().min(127)].copy_from_slice(&tip[..tip.len().min(127)]);

        unsafe {
            if Shell_NotifyIconW(NIM_ADD, &mut nid as *mut NOTIFYICONDATAW) == 0 {
                return Err("failed to add tray icon".to_string());
            }
        }

        Ok(Self {
            tray_hwnd,
            main_hwnd,
            tray_class_name,
            main_class_name,
        })
    }

    fn run(self) -> ! {
        let mut msg = unsafe { std::mem::zeroed::<MSG>() };
        unsafe {
            loop {
                let result = GetMessageW(&mut msg, 0, 0, 0);
                if result <= 0 {
                    break;
                }
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }
        cleanup();
        std::process::exit(0);
    }
}

impl Drop for TrayHandle {
    fn drop(&mut self) {
        cleanup();
    }
}

fn create_main_window(class_name: &[u16], hinstance: HINSTANCE) -> Result<HWND, String> {
    let wc = WNDCLASSW {
        style: 0,
        lpfnWndProc: Some(main_window_proc),
        cbClsExtra: 0,
        cbWndExtra: 0,
        hInstance: hinstance,
        hIcon: app_icon_handle(),
        hCursor: unsafe { LoadCursorW(0, IDC_ARROW) },
        hbrBackground: 0,
        lpszMenuName: std::ptr::null(),
        lpszClassName: class_name.as_ptr(),
    };

    unsafe {
        if RegisterClassW(&wc) == 0 {
            return Err("failed to register main window class".to_string());
        }
    }

    let hwnd = unsafe {
        CreateWindowExW(
            0,
            class_name.as_ptr(),
            to_wstring("AlienVox").as_ptr(),
            WS_OVERLAPPEDWINDOW,
            CW_USEDEFAULT,
            0,
            520,
            260,
            0 as HWND,
            0,
            hinstance,
            std::ptr::null_mut(),
        )
    };
    if hwnd == 0 as HWND {
        return Err("failed to create main window".to_string());
    }

    unsafe {
        SendMessageW(hwnd, WM_SETICON, ICON_BIG as WPARAM, app_icon_handle() as LPARAM);

        let _label = CreateWindowExW(
            0,
            to_wstring("STATIC").as_ptr(),
            to_wstring("AlienVox is running from the tray. Use the menu to show Preferences or quit.").as_ptr(),
            WS_CHILD | WS_VISIBLE,
            24,
            24,
            460,
            24,
            hwnd,
            0 as HMENU,
            hinstance,
            std::ptr::null_mut(),
        );

        let _button = CreateWindowExW(
            0,
            to_wstring("BUTTON").as_ptr(),
            to_wstring("Close").as_ptr(),
            WS_CHILD | WS_VISIBLE | (BS_DEFPUSHBUTTON as u32),
            210,
            160,
            100,
            32,
            hwnd,
            1001 as HMENU,
            hinstance,
            std::ptr::null_mut(),
        );

        ShowWindow(hwnd, SW_HIDE);
    }
    Ok(hwnd)
}

fn create_tray_window(class_name: &[u16], hinstance: HINSTANCE) -> Result<HWND, String> {
    let wc = WNDCLASSW {
        style: 0,
        lpfnWndProc: Some(tray_window_proc),
        cbClsExtra: 0,
        cbWndExtra: 0,
        hInstance: hinstance,
        hIcon: app_icon_handle(),
        hCursor: unsafe { LoadCursorW(0, IDC_ARROW) },
        hbrBackground: 0,
        lpszMenuName: std::ptr::null(),
        lpszClassName: class_name.as_ptr(),
    };

    unsafe {
        if RegisterClassW(&wc) == 0 {
            return Err("failed to register tray window class".to_string());
        }
    }

    let hwnd = unsafe {
        CreateWindowExW(
            0,
            class_name.as_ptr(),
            to_wstring("AlienVoxTrayWindow").as_ptr(),
            WS_OVERLAPPEDWINDOW,
            CW_USEDEFAULT,
            0,
            CW_USEDEFAULT,
            0,
            0 as HWND,
            0,
            hinstance,
            std::ptr::null_mut(),
        )
    };
    if hwnd == 0 as HWND {
        return Err("failed to create tray window".to_string());
    }

    unsafe {
        ShowWindow(hwnd, SW_HIDE);
    }
    Ok(hwnd)
}

fn cleanup() {
    let mut state_lock = state().lock().unwrap();
    if state_lock.quitting {
        return;
    }
    state_lock.quitting = true;
    let tray_hwnd = state_lock.tray_hwnd;
    let main_hwnd = state_lock.main_hwnd;
    let tray_class_name = state_lock.tray_class_name.clone();
    let main_class_name = state_lock.main_class_name.clone();
    drop(state_lock);

    unsafe {
        let mut nid = std::mem::zeroed::<NOTIFYICONDATAW>();
        nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
        nid.hWnd = tray_hwnd;
        nid.uID = 1;
        Shell_NotifyIconW(NIM_DELETE, &mut nid as *mut NOTIFYICONDATAW);
        if main_hwnd != 0 as HWND {
            DestroyWindow(main_hwnd);
        }
        if tray_hwnd != 0 as HWND {
            DestroyWindow(tray_hwnd);
        }
        if !tray_class_name.is_empty() {
            UnregisterClassW(tray_class_name.as_ptr(), GetModuleHandleW(std::ptr::null()));
        }
        if !main_class_name.is_empty() {
            UnregisterClassW(main_class_name.as_ptr(), GetModuleHandleW(std::ptr::null()));
        }
    }
}

fn show_main_window() {
    let state_lock = state().lock().unwrap();
    let hwnd = state_lock.main_hwnd;
    drop(state_lock);
    if hwnd != 0 as HWND {
        unsafe {
            ShowWindow(hwnd, SW_SHOW);
            SetForegroundWindow(hwnd);
        }
    }
}

fn hide_main_window() {
    let state_lock = state().lock().unwrap();
    let hwnd = state_lock.main_hwnd;
    drop(state_lock);
    if hwnd != 0 as HWND {
        unsafe {
            ShowWindow(hwnd, SW_HIDE);
        }
    }
}

fn show_preferences_dialog() {
    let mut state_lock = state().lock().unwrap();
    if state_lock.preferences_hwnd != 0 as HWND {
        unsafe {
            ShowWindow(state_lock.preferences_hwnd, SW_SHOW);
            SetForegroundWindow(state_lock.preferences_hwnd);
        }
        return;
    }

    let class_name = to_wstring("AlienVoxPreferencesDialog");
    let hinstance = unsafe { GetModuleHandleW(std::ptr::null()) as HINSTANCE };
    state_lock.preferences_class_name = class_name.clone();
    drop(state_lock);

    let wc = WNDCLASSW {
        style: 0,
        lpfnWndProc: Some(preferences_window_proc),
        cbClsExtra: 0,
        cbWndExtra: 0,
        hInstance: hinstance,
        hIcon: app_icon_handle(),
        hCursor: unsafe { LoadCursorW(0, IDC_ARROW) },
        hbrBackground: 0,
        lpszMenuName: std::ptr::null(),
        lpszClassName: class_name.as_ptr(),
    };

    unsafe {
        if RegisterClassW(&wc) == 0 {
            eprintln!("failed to register preferences dialog class");
            return;
        }
    }

    let hwnd = unsafe {
        CreateWindowExW(
            0,
            class_name.as_ptr(),
            to_wstring("AlienVox Preferences").as_ptr(),
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            420,
            220,
            0 as HWND,
            0 as HMENU,
            hinstance,
            std::ptr::null_mut(),
        )
    };

    if hwnd == 0 as HWND {
        eprintln!("failed to create preferences dialog");
        return;
    }

    unsafe {
        SendMessageW(hwnd, WM_SETICON, ICON_BIG as WPARAM, app_icon_handle() as LPARAM);
    }

    let label = unsafe {
        CreateWindowExW(
            0,
            to_wstring("STATIC").as_ptr(),
            to_wstring("Preferences and settings will appear here.").as_ptr(),
            WS_CHILD | WS_VISIBLE,
            24,
            24,
            360,
            24,
            hwnd,
            0 as HMENU,
            hinstance,
            std::ptr::null_mut(),
        )
    };
    if label != 0 as HWND {
        unsafe {
            SetWindowTextW(label, to_wstring("Preferences and settings will appear here.").as_ptr());
        }
    }

    let button = unsafe {
        CreateWindowExW(
            0,
            to_wstring("BUTTON").as_ptr(),
            to_wstring("Close").as_ptr(),
            WS_CHILD | WS_VISIBLE | (BS_DEFPUSHBUTTON as u32),
            150,
            120,
            100,
            28,
            hwnd,
            1 as HMENU,
            hinstance,
            std::ptr::null_mut(),
        )
    };
    if button == 0 as HWND {
        eprintln!("failed to create preferences dialog button");
    }

    let mut state_lock = state().lock().unwrap();
    state_lock.preferences_hwnd = hwnd;
}

fn show_context_menu() {
    let state_lock = state().lock().unwrap();
    let hwnd = state_lock.tray_hwnd;
    drop(state_lock);

    let menu = unsafe { CreatePopupMenu() };
    unsafe {
        AppendMenuW(menu, MF_STRING | MF_ENABLED, 1001, to_wstring("Preferences...").as_ptr());
        AppendMenuW(menu, MF_STRING | MF_ENABLED, 1002, to_wstring("Quit").as_ptr());
    }

    let mut cursor = POINT { x: 0, y: 0 };
    unsafe {
        GetCursorPos(&mut cursor);
        let command = TrackPopupMenuEx(
            menu,
            TPM_RETURNCMD | TPM_LEFTALIGN | TPM_TOPALIGN | TPM_RIGHTBUTTON,
            cursor.x,
            cursor.y,
            hwnd,
            std::ptr::null_mut(),
        );
        DestroyMenu(menu);
        match command as u32 {
            1001 => show_preferences_dialog(),
            1002 => cleanup(),
            _ => {}
        }
    }
}

unsafe extern "system" fn tray_window_proc(
    _hwnd: HWND,
    msg: u32,
    _wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_DESTROY => {
            PostQuitMessage(0);
            0
        }
        msg if msg == WM_USER + 1 => {
            let notification = (lparam & 0xffff) as u32;
            match notification {
                0x203 => show_main_window(),
                0x205 => show_context_menu(),
                _ => {}
            }
            0
        }
        _ => DefWindowProcW(_hwnd, msg, _wparam, lparam),
    }
}

unsafe extern "system" fn main_window_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    _lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_COMMAND => {
            let notification = (wparam as u32 >> 16) as u32;
            let control_id = (wparam & 0xffff) as u32;
            if notification == BN_CLICKED as u32 && control_id == 1001 {
                hide_main_window();
            }
            0
        }
        WM_CLOSE => {
            hide_main_window();
            0
        }
        WM_DESTROY => {
            let mut state_lock = state().lock().unwrap();
            if state_lock.main_hwnd == hwnd {
                state_lock.main_hwnd = 0 as HWND;
            }
            0
        }
        _ => DefWindowProcW(hwnd, msg, wparam, _lparam),
    }
}

unsafe extern "system" fn preferences_window_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    match msg {
        WM_COMMAND => {
            if (wparam as u32 >> 16) == BN_CLICKED as u32 {
                let notification_id = (wparam & 0xffff) as u32;
                if notification_id == 1 {
                    DestroyWindow(hwnd);
                }
            }
            0
        }
        WM_CLOSE => {
            DestroyWindow(hwnd);
            0
        }
        WM_DESTROY => {
            let mut state_lock = state().lock().unwrap();
            if state_lock.preferences_hwnd == hwnd {
                state_lock.preferences_hwnd = 0 as HWND;
            }
            0
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

fn app_icon_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src/assets/icons/icon.ico")
}

fn app_icon_handle() -> isize {
    load_icon(&app_icon_path())
}

fn load_icon(path: &std::path::Path) -> isize {
    let wide = to_wstring(path.to_string_lossy().as_ref());
    let icon = unsafe { LoadImageW(0, wide.as_ptr(), 1, 0, 0, LR_LOADFROMFILE) };
    if icon != 0 {
        icon
    } else {
        unsafe { LoadIconW(0, IDI_APPLICATION) }
    }
}

fn to_wstring(value: &str) -> Vec<u16> {
    OsStr::new(value).encode_wide().chain(std::iter::once(0)).collect()
}
