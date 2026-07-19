"""Structured per-session logger — mirrors Rust's tracing format.

Every line written to:
  1. stderr  (always, for `run.py app` console visibility)
  2. %LOCALAPPDATA%/com.alientech.alienvox/logs/session-<id>_AlienVox.log

Format (matches Rust):
  [LEVEL]  2026-07-19T16:43:07.123  component  message

Levels: TRACE  INFO  WARN  ERROR

Usage:
    from .logger import get_logger
    log = get_logger("sapi")
    log.info("Speak() submitted")
    log.trace("voice_id=%s rate=%d", voice_id, rate)
"""
from __future__ import annotations

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import IO


_lock = threading.Lock()
_log_file: IO[str] | None = None
_session_id: str = ""
_log_path: Path | None = None


def init(session_id: str) -> Path:
    """Call once at startup with the telemetry session_id.

    Returns the path of the log file so the startup banner can print it.
    """
    global _session_id, _log_file, _log_path

    _session_id = session_id

    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    log_dir = base / "com.alientech.alienvox" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _log_path = log_dir / f"session-{session_id}_AlienVox.log"

    try:
        _log_file = _log_path.open("a", encoding="utf-8", buffering=1)
    except Exception:
        _log_file = None

    return _log_path


def get_logger(component: str) -> "_Logger":
    return _Logger(component)


# ── Internal ──────────────────────────────────────────────────────────────────

def _write(level: str, component: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    line = f"[{level:<5}]  {ts}  {component:<12}  {msg}"
    with _lock:
        try:
            print(line, file=sys.stderr, flush=True)
        except Exception:
            pass
        if _log_file is not None:
            try:
                _log_file.write(line + "\n")
                _log_file.flush()
            except Exception:
                pass


class _Logger:
    def __init__(self, component: str) -> None:
        self._c = component

    def trace(self, msg: str, *args: object) -> None:
        _write("TRACE", self._c, msg % args if args else msg)

    def info(self, msg: str, *args: object) -> None:
        _write("INFO", self._c, msg % args if args else msg)

    def warn(self, msg: str, *args: object) -> None:
        _write("WARN", self._c, msg % args if args else msg)

    def error(self, msg: str, *args: object) -> None:
        _write("ERROR", self._c, msg % args if args else msg)
