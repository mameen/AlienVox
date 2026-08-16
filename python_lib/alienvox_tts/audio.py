"""Shared audio playback layer.

Copied out of `python_app/src/audio_player.py`, including a real fix
already found and shipped in the app (not theoretical — confirmed by ear):
`sd.wait()` returns once samples are handed to the OS mixer, not once the
physical speaker has actually finished rendering them. On Windows WASAPI
shared-mode output in particular there's a real hardware buffer tail that
gets audibly cut off if the calling process exits (or moves on) right after
`sd.wait()` returns — the `_PLAYBACK_TAIL_SETTLE_S` sleep below lets that
tail actually finish before `play_audio()` hands control back.

Uses `sounddevice` for cross-platform output (Windows, Linux, macOS). All
functions are thread-safe; only one stream plays at a time — calling
`play_audio()` while something is already playing stops the current
playback first, it does not queue.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd

_lock = threading.Lock()

_PLAYBACK_TAIL_SETTLE_S = 0.6


def play_audio(data: np.ndarray, sample_rate: int) -> None:
    """Play a float32 numpy array synchronously (blocks until finished,
    including the hardware tail settle). Stops any current playback first."""
    stop_playback()
    with _lock:
        sd.play(data, sample_rate)
    sd.wait()
    time.sleep(_PLAYBACK_TAIL_SETTLE_S)


def stop_playback() -> None:
    """Interrupt any active playback. Safe to call when nothing is playing."""
    try:
        sd.stop()
    except Exception:
        pass
