"""Persistent volume level — separate from SpeakParams.volume.

SpeakParams.volume (see base.py) is a PER-CALL override — "make this one
utterance quieter." This module is a different thing: a process-lifetime
DEFAULT volume level that every synthesize()/speak() call uses when no
per-call volume is given, with absolute ("set to 40%") and relative
("10% louder/quieter") controls — the kind of thing a long-lived process
(the MCP server, in particular) genuinely needs, since "make it quieter"
in one call should stay quieter for the next call too, not reset.

Module-level state, not a class — there's exactly one volume level per
process, same as a physical volume knob has exactly one position; nothing
here is meant to be instantiated per-caller.
"""
from __future__ import annotations

_current_volume: int = 100  # 0 (silent) .. 100 (full) — matches SpeakParams.volume's range


def get_volume() -> int:
    """Current persistent volume level, 0..100."""
    return _current_volume


def set_volume(percent: int) -> int:
    """Set the persistent volume level absolutely. Clamps to 0..100 rather
    than raising on an out-of-range value — same "clamp, don't crash"
    policy as SpeakParams.volume's own downstream handling. Returns the
    clamped value actually applied."""
    global _current_volume
    _current_volume = max(0, min(100, percent))
    return _current_volume


def volume_up(step: int = 10) -> int:
    """Raise the persistent volume by `step` percentage points (default
    10, per the "goes up/down 10%" requirement), clamped at 100. Returns
    the new level."""
    return set_volume(_current_volume + step)


def volume_down(step: int = 10) -> int:
    """Lower the persistent volume by `step` percentage points (default
    10), clamped at 0. Returns the new level."""
    return set_volume(_current_volume - step)
