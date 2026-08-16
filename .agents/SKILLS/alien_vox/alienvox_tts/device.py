"""Shared CPU/CUDA device detection.

Copied out of `python_app/src/device.py` verbatim in logic (same real bug
this guards against — see below) so every engine in this library picks a
device the same, correct way instead of each reimplementing (and
re-risking) the same check.

`torch.cuda.is_available()` alone is not a reliable signal: it can return
True even when zero CUDA devices are actually visible to the process (for
example under a `CUDA_VISIBLE_DEVICES=""` override, or certain broken
driver states) — it only reports whether the CUDA *runtime* is loadable,
not that a usable device is actually selected. `device_count() > 0` is the
real signal.
"""
from __future__ import annotations


def cuda_available() -> bool:
    """True if torch can see at least one real, usable CUDA device."""
    try:
        import torch
        return torch.cuda.is_available() and torch.cuda.device_count() > 0
    except Exception:
        # torch not installed, or querying the driver failed for any
        # reason — fail closed to CPU rather than raise, since device
        # selection should never be the reason synthesis can't proceed.
        return False


def select_device(prefer: str | None = None) -> str:
    """Return the device string to use for model loading/inference.

    prefer=None (default): auto — "cuda" if a real CUDA device is usable,
        else "cpu". This is the auto-detect behavior; callers that want a
        CPU-by-default policy (e.g. the MCP server, matching the app's own
        `run.py` CPU-default philosophy) should NOT rely on this default —
        pass prefer="cpu" explicitly instead and only pass "cuda" when a
        caller explicitly opts in.
    prefer="cpu": always returns "cpu", regardless of GPU availability.
    prefer="cuda"/"gpu": returns "cuda" if usable, else falls back to "cpu"
        (never raises just because a GPU was requested but isn't present —
        callers that need to know whether their request was honored should
        compare their input against this function's return value).
    """
    if prefer == "cpu":
        return "cpu"
    # prefer in ("cuda", "gpu") or prefer is None (auto-detect): same check either way.
    return "cuda" if cuda_available() else "cpu"
