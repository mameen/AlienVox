"""Global hotkey listener using pynput."""
from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


def start_listener(hotkey: str, callback: Callable[[], None]) -> keyboard.GlobalHotKeys:
    """Start a background global hotkey listener. Returns the listener (call .stop() to clean up)."""
    listener = keyboard.GlobalHotKeys({hotkey: callback})
    listener.start()
    return listener
