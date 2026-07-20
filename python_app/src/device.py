"""Shared CUDA device detection for ML engines.

torch.cuda.is_available() can return True with zero visible devices (e.g.
under CUDA_VISIBLE_DEVICES="" or an out-of-range index) — it only reports
whether the CUDA driver/runtime is loadable, not that a device is actually
selected. device_count() > 0 is the real signal. Centralized here so every
engine's device selection is consistent instead of each reimplementing
(and re-risking) the same check.
"""
from __future__ import annotations


def cuda_available() -> bool:
    """True if torch can see at least one CUDA device."""
    try:
        import torch
        return torch.cuda.is_available() and torch.cuda.device_count() > 0
    except Exception:
        return False


def select_device() -> str:
    """Return 'cuda' if a CUDA device is usable, else 'cpu'."""
    return "cuda" if cuda_available() else "cpu"
