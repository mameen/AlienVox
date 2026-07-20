"""Structured per-session logger — mirrors Rust's tracing format.

Every line written to:
  1. stderr  (always, for `run.py app` console visibility)
  2. python_app/.logs/session-<id>_AlienVox.log  (dev — repo-local, gitignored)
  3. %LOCALAPPDATA%/com.alientech.alienvox/logs/session-<id>_AlienVox.log  (production)

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
from typing import TextIO

_lock = threading.Lock()
_log_files: list[TextIO] = []
_session_id: str = ""
_log_path: Path | None = None  # primary path shown in startup banner (dev sink)


def init(session_id: str) -> Path:
    """Call once at startup with the telemetry session_id.

    Returns the path of the dev log file so the startup banner can print it.
    Session ID format: session-<unix_ms>  (matches Rust convention).
    """
    global _session_id, _log_files, _log_path

    _session_id = session_id
    filename = f"{session_id}_AlienVox.log"

    # Dev sink: repo-local .logs/ — easy to find during development.
    dev_log_dir = Path(__file__).parent.parent / ".logs"
    _log_path = dev_log_dir / filename

    # Production sink: %LOCALAPPDATA%/com.alientech.alienvox/logs/
    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    prod_log_path = base / "com.alientech.alienvox" / "logs" / filename

    for path in (dev_log_dir / filename, prod_log_path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _log_files.append(path.open("a", encoding="utf-8", buffering=1))
        except Exception:
            pass

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
        for f in _log_files:
            try:
                f.write(line + "\n")
                f.flush()
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
