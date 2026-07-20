"""Shared audio playback layer for ML engines.

Uses sounddevice for cross-platform output (Windows, Linux, Mac).
All functions are thread-safe. Only one stream plays at a time;
calling play_audio() while audio is playing will stop the current stream first.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    pass

_lock = threading.Lock()
_current_stream: sd.OutputStream | None = None


def play_audio(data: np.ndarray, sample_rate: int) -> None:
    """Play float32 numpy array synchronously. Stops any current playback first."""
    global _current_stream

    stop_playback()

    with _lock:
        sd.play(data, sample_rate)

    sd.wait()


def stop_playback() -> None:
    """Interrupt any active sounddevice playback."""
    try:
        sd.stop()
    except Exception:
        pass
