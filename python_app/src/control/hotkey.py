"""Global hotkey listener using pynput."""
from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard


def start_listener(bindings: dict[str, Callable[[], None]]) -> keyboard.GlobalHotKeys:
    """Start a background global hotkey listener for one or more combos.
    Returns the listener (call .stop() to clean up)."""
    listener = keyboard.GlobalHotKeys(bindings)
    listener.start()
    return listener


def enhanced_variant_of(hotkey: str) -> str:
    """The "Play Enhanced" hotkey is the primary hotkey plus Shift — e.g.
    '<alt>+<esc>' -> '<shift>+<alt>+<esc>'. Derived rather than a separate
    configurable field: it's always "the same combo, plus Shift"."""
    return f"<shift>+{hotkey}"
