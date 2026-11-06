#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run identity and structured logging, so a transcription run can be audited afterwards.

A batch of recordings can run for an hour. When it ends, three questions need
answers without a debugger: *what ran, on which files, with which settings*;
*what finished and what failed*; and *where did the outputs go*. This module
provides the smallest thing that answers them: a run ID, JSONL events, and a
final summary.

What is recorded
----------------
* A **run ID**: ``<operation>-<DATETIME STAMP>-<4 hex>``. The stamp follows the
  library convention (``YYYYMMDDHHmmss`` in Pacific time), the suffix keeps two
  runs started in the same second apart.
* **Events**, one JSON object per line: ``ts`` (UTC, ISO 8601), ``level``,
  ``event``, ``run_id`` plus whatever fields the caller adds. Stable event
  names: ``run_started``, ``input_resolved``, ``item_started``,
  ``item_complete``, ``item_skipped``, ``item_failed``, ``run_finished``.
* A **summary**: counts, elapsed time, outputs. Printed at the end and
  returned, so callers and tests can read it.

Privacy: events carry file *names*, counts, durations and settings. They never
carry transcript text or audio content, because a log is the file most likely to
be pasted into a bug report.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import secrets
import sys
import time
from typing import Any, Optional


def datetime_stamp() -> str:
    """The library's DATETIME STAMP: ``YYYYMMDDHHmmss`` in Pacific time.

    Falls back to local time if the time-zone database is unavailable (a
    Windows Python without the ``tzdata`` package); the fallback only affects
    the label in a run ID, never any output.
    """
    try:
        from zoneinfo import ZoneInfo

        now = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        now = datetime.datetime.now()
    return now.strftime("%Y%m%d%H%M%S")


def new_run_id(operation: str) -> str:
    """Create ``<operation>-<DATETIME STAMP>-<4 hex>``."""
    return f"{operation}-{datetime_stamp()}-{secrets.token_hex(2)}"


class RunLog:
    """Collects events for one run; optionally mirrors them to a JSONL file.

    Parameters
    ----------
    operation:
        Short name used in the run ID, for example ``"transcribe"``.
    log_dir:
        If given, events are appended to ``<log_dir>/<run_id>.jsonl``. If
        ``None`` nothing is written to disk; events are still counted so the
        summary is complete.
    quiet:
        Suppress the console lines (the JSONL file is unaffected).
    """

    def __init__(self, operation: str, log_dir: Optional[str | os.PathLike] = None, quiet: bool = False) -> None:
        self.run_id = new_run_id(operation)
        self.quiet = quiet
        self.started = time.monotonic()
        self.counts: dict[str, int] = {}
        self.outputs: list[str] = []
        self.path: Optional[pathlib.Path] = None
        if log_dir:
            self.path = pathlib.Path(log_dir) / f"{self.run_id}.jsonl"
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, name: str, level: str = "INFO", **fields: Any) -> dict[str, Any]:
        """Record one event and return it. Unknown field types are stringified."""
        record = {
            "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level, "event": name, "run_id": self.run_id, **fields,
        }
        self.counts[name] = self.counts.get(name, 0) + 1
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    def say(self, message: str, error: bool = False) -> None:
        """Print a short human line (stderr for errors); a no-op when `quiet`."""
        if not self.quiet:
            print(message, file=sys.stderr if error else sys.stdout, flush=True)

    def output(self, path: str | os.PathLike) -> None:
        """Remember a file this run produced, for the summary."""
        self.outputs.append(str(path))

    def summary(self) -> dict[str, Any]:
        """Counts, elapsed seconds and outputs so far."""
        return {
            "run_id": self.run_id,
            "elapsed_s": round(time.monotonic() - self.started, 1),
            "complete": self.counts.get("item_complete", 0),
            "skipped": self.counts.get("item_skipped", 0),
            "failed": self.counts.get("item_failed", 0),
            "outputs": list(self.outputs),
            "log": str(self.path) if self.path else None,
        }
