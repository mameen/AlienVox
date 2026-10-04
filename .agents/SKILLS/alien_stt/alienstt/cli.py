#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Small helpers shared by every script in ../scripts, so each script stays thin.

The scripts only parse arguments, call the library and report. Anything two of
them need lives here (or in the library proper), never copy-pasted.
"""
from __future__ import annotations

import sys
from typing import NoReturn


def setup_console() -> None:
    """Make stdout/stderr UTF-8 so Arabic, CJK and accented text print on Windows.

    Windows consoles default to a legacy code page and raise
    ``UnicodeEncodeError`` on the first non-Latin character. Reconfiguring is a
    no-op where the streams are already UTF-8 or cannot be reconfigured.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def fail(message: str, code: int = 1) -> NoReturn:
    """Print ``ERROR: message`` to stderr and exit; never a silent non-zero exit."""
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def human_duration(seconds: float) -> str:
    """``3725.4`` -> ``1h 02m 05s``; ``42`` -> ``42s``. For console reports."""
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s" if m else f"{s}s"
