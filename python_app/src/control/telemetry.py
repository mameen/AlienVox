"""Telemetry sink — JSONL file + stderr, never network.

Every event is written to:
  1. A local JSONL file (append-only, one JSON object per line).
  2. stderr as:  ALIENVOX_TELEMETRY <compact-json>

Write failures are silently swallowed — telemetry must never crash the app.

Usage:
    tel = Telemetry()               # session_id generated at startup
    rid = tel.new_request_id()
    tel.emit("speak.triggered", request_id=rid, engine="sapi5", ...)
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _appdata_sink(session_id: str) -> Path:
    import os
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "com.alientech.alienvox" / "telemetry" / f"{session_id}_AlienVox.jsonl"


def _dev_sink(session_id: str) -> Path:
    """Repo-local .logs/ dir — easy to tail during dev."""
    return Path(__file__).parent.parent.parent / ".logs" / f"{session_id}_AlienVox.jsonl"


class Telemetry:
    def __init__(self, sink: Path | None = None) -> None:
        self._session_id = f"session-{_now_ms()}"
        if sink is not None:
            # Explicit override (tests, custom callers) — this is the only sink.
            self._sinks: list[Path] = [sink]
        elif getattr(sys, "frozen", False):
            # Frozen/installed build only — never repo-local (see main.py's
            # module docstring for why we DON'T ship a python_app checkout
            # alongside a frozen install).
            self._sinks = [_appdata_sink(self._session_id)]
        else:
            # HARD RULE (not negotiable — see docs/issues/issue_002.md):
            # dev NEVER writes into %LOCALAPPDATA%\com.alientech.alienvox —
            # that's the real install's data. Previously this wrote to BOTH
            # sinks unconditionally, meaning every dev run silently mixed
            # its telemetry into the same folder a real installed copy
            # uses. Dev-only writes to the repo-local sink.
            self._sinks = [_dev_sink(self._session_id)]

    @property
    def session_id(self) -> str:
        return self._session_id

    def new_request_id(self) -> str:
        return str(uuid.uuid4())

    def emit(
        self,
        event: str,
        *,
        request_id: str = "",
        engine: str = "",
        model: str = "",
        voice: str = "",
        text_chars: int = 0,
        text_bytes: int = 0,
        latency_ms: int = 0,
        status: str = "ok",
        detail: str | None = None,
        **extra: Any,
    ) -> None:
        record: dict[str, Any] = {
            "timestamp_unix_ms": _now_ms(),
            "event": event,
            "session_id": self._session_id,
            "request_id": request_id,
            "engine": engine,
            "model": model,
            "voice": voice,
            "text_chars": text_chars,
            "text_bytes": text_bytes,
            "latency_ms": latency_ms,
            "status": status,
            "detail": detail,
        }
        record.update(extra)
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
        self._write_file(line)
        self._write_stderr(line)

    def _write_file(self, line: str) -> None:
        for sink in self._sinks:
            try:
                sink.parent.mkdir(parents=True, exist_ok=True)
                with sink.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    f.flush()
            except Exception:
                pass

    def _write_stderr(self, line: str) -> None:
        try:
            print(f"ALIENVOX_TELEMETRY {line}", file=sys.stderr, flush=True)
        except Exception:
            pass
