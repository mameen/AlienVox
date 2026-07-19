"""Windows text capture: UI Automation → clipboard fallback.

Tier 1: UIAutomation active selection (zero clipboard side-effects)
Tier 2: Ctrl+C clipboard copy (50ms timeout)
"""
from __future__ import annotations

import sys
import time

if sys.platform != "win32":
    raise ImportError("capture is Windows-only")

import win32clipboard  # type: ignore
import win32con  # type: ignore
import win32api  # type: ignore


def get_selected_text(timeout_ms: int = 50) -> str:
    # Tier 1: try UIA (no side-effects)
    text = _uia_selection()
    if text:
        return text

    # Tier 2: Ctrl+C and read clipboard
    return _clipboard_copy(timeout_ms)


def _uia_selection() -> str:
    try:
        import comtypes.client  # type: ignore
        uia = comtypes.client.CreateObject(
            "{FF48DBA4-60EF-4201-AA87-54103EEF594E}",
            interface=comtypes.gen.UIAutomationClient.IUIAutomation,  # type: ignore
        )
        focused = uia.GetFocusedElement()
        pattern = focused.GetCurrentPattern(10014)  # UIA_TextPatternId
        if pattern:
            sel = pattern.GetSelection()
            if sel.Length > 0:
                return sel.GetElement(0).GetText(-1)
    except Exception:
        pass
    return ""


def _clipboard_copy(timeout_ms: int) -> str:
    # Save clipboard, simulate copy, read, restore
    old = _read_clipboard()
    win32api.keybd_event(0x11, 0, 0, 0)          # Ctrl down
    win32api.keybd_event(0x43, 0, 0, 0)          # C down
    win32api.keybd_event(0x43, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(0x11, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(timeout_ms / 1000)
    text = _read_clipboard()
    if old:
        _write_clipboard(old)
    return text


def _read_clipboard() -> str:
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return data or ""
    except Exception:
        return ""
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    return ""


def _write_clipboard(text: str) -> None:
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    except Exception:
        pass
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
