"""Windows text capture.

Tier 1: WM_COPY to the focused control — no keyboard simulation, no
        clipboard side-effects for apps that handle WM_COPY natively.
Tier 2: Ctrl+C clipboard copy — universal fallback, saves/restores clipboard.

Both tiers are pure win32; comtypes / UIAutomation is NOT required.
"""
from __future__ import annotations

import sys
import time

if sys.platform != "win32":
    raise ImportError("capture is Windows-only")

import win32api       # type: ignore
import win32clipboard # type: ignore
import win32con       # type: ignore
import win32gui       # type: ignore
import win32process   # type: ignore


# ── Public API ────────────────────────────────────────────────────────────────

def get_selected_text(timeout_ms: int = 80) -> str:
    """Return the currently selected text, or '' if none is found."""
    text = _wm_copy_selection(timeout_ms // 2)
    if text:
        return text
    return _clipboard_copy(timeout_ms // 2)


# ── Tier 1: WM_COPY ───────────────────────────────────────────────────────────

def _wm_copy_selection(wait_ms: int) -> str:
    """Send WM_COPY to the focused control and read the result."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return ""

        # Attach to the foreground thread so GetFocus() sees its focused child.
        tid, _pid = win32process.GetWindowThreadProcessId(hwnd)
        our_tid = win32api.GetCurrentThreadId()
        attached = False
        if tid != our_tid:
            try:
                win32process.AttachThreadInput(our_tid, tid, True)
                attached = True
            except Exception:
                pass

        try:
            focused = win32gui.GetFocus() or hwnd
        finally:
            if attached:
                try:
                    win32process.AttachThreadInput(our_tid, tid, False)
                except Exception:
                    pass

        old = _read_clipboard()
        win32api.SendMessage(focused, win32con.WM_COPY, 0, 0)
        time.sleep(wait_ms / 1000)
        new = _read_clipboard()

        # Only accept the result if the clipboard actually changed.
        if new and new != old:
            return new
    except Exception:
        pass
    return ""


# ── Tier 2: Ctrl+C ───────────────────────────────────────────────────────────

def _clipboard_copy(wait_ms: int) -> str:
    """Simulate Ctrl+C, read clipboard, then restore the previous content."""
    old = _read_clipboard()

    # VK_CONTROL = 0x11, VK_C = 0x43
    win32api.keybd_event(0x11, 0, 0, 0)
    win32api.keybd_event(0x43, 0, 0, 0)
    win32api.keybd_event(0x43, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)

    time.sleep(wait_ms / 1000)
    text = _read_clipboard()

    # Restore the previous clipboard so the user doesn't notice we touched it.
    if old is not None:
        _write_clipboard(old)

    return text or ""


# ── Clipboard helpers ─────────────────────────────────────────────────────────

def _read_clipboard() -> str:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.01)
    return ""


def _write_clipboard(text: str) -> None:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                return
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.01)
