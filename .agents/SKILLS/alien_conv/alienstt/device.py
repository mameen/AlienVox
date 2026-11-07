#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CPU/CUDA device selection, shared by every engine.

Why not just `torch.cuda.is_available()`
---------------------------------------
That call can return ``True`` when zero CUDA devices are actually visible to
the process (a ``CUDA_VISIBLE_DEVICES=""`` override, a half-broken driver). It
reports whether the CUDA *runtime* loads, not whether a usable device is
selected. `device_count() > 0` is the real signal, so both are checked.

Why the default here is ``auto`` and not ``cpu``
------------------------------------------------
Text-to-speech in this repository defaults to CPU on purpose: it plays audio
interactively and must not grab a GPU someone else is using. Speech-to-text is
the opposite workload. It is batch work whose runtime is dominated by the model
(large Whisper models take minutes per hour of audio on a GPU and far longer on
a CPU). So `auto` prefers a GPU when one is really there, and anyone who needs
the CPU says ``--device cpu``.
"""
from __future__ import annotations

from typing import Optional


def cuda_available() -> bool:
    """True if torch can see at least one real, usable CUDA device.

    Fails closed: if torch is not installed or the driver query throws, the
    answer is ``False`` and work proceeds on CPU rather than crashing here.
    """
    try:
        import torch

        return bool(torch.cuda.is_available() and torch.cuda.device_count() > 0)
    except Exception:
        return False


def select_device(prefer: Optional[str] = "auto") -> str:
    """Resolve a user preference to ``"cuda"`` or ``"cpu"``.

    * ``"cpu"``: always CPU.
    * ``"cuda"`` / ``"gpu"``: CUDA if usable, otherwise CPU. A request for a GPU
      that is absent never raises; compare the return value with the request
      if you need to know whether it was honoured (the CLI prints it).
    * ``"auto"`` / ``None``: CUDA if usable, otherwise CPU.
    """
    if prefer == "cpu":
        return "cpu"
    return "cuda" if cuda_available() else "cpu"
