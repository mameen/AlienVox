"""Shared audio playback layer for ML engines.

Uses sounddevice for cross-platform output (Windows, Linux, Mac).
All functions are thread-safe. Only one stream plays at a time;
calling play_audio() while audio is playing will stop the current stream first.
"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    pass

_lock = threading.Lock()
_current_stream: sd.OutputStream | None = None

# sd.wait() returns once all samples are handed to the OS mixer, not once
# the physical speaker has actually finished rendering them — on Windows
# WASAPI shared-mode output in particular, there's a real hardware buffer
# tail (confirmed by ear: a long real synthesis result got audibly cut
# short right at the end) that isn't accounted for by sd.wait() alone.
# This settle delay lets that tail actually play out before play_audio()
# returns and the caller (e.g. a short-lived CLI process) can exit.
_PLAYBACK_TAIL_SETTLE_S = 0.3


def play_audio(data: np.ndarray, sample_rate: int) -> None:
    """Play float32 numpy array synchronously. Stops any current playback first."""
    global _current_stream

    stop_playback()

    with _lock:
        sd.play(data, sample_rate)

    sd.wait()
    time.sleep(_PLAYBACK_TAIL_SETTLE_S)


def stop_playback() -> None:
    """Interrupt any active sounddevice playback."""
    try:
        sd.stop()
    except Exception:
        pass
