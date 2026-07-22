"""Tests for src/logger.py — structured session logger."""
from __future__ import annotations

import sys
from pathlib import Path


def test_get_logger_returns_logger():
    from src.logger import get_logger
    log = get_logger("test")
    assert log is not None


def test_logger_writes_to_stderr(capsys):
    from src.logger import get_logger
    log = get_logger("test")
    log.info("hello %s", "world")
    captured = capsys.readouterr()
    assert "hello world" in captured.err
    assert "INFO" in captured.err
    assert "test" in captured.err


def test_logger_all_levels(capsys):
    from src.logger import get_logger
    log = get_logger("lvl")
    log.trace("t")
    log.info("i")
    log.warn("w")
    log.error("e")
    captured = capsys.readouterr()
    assert "TRACE" in captured.err
    assert "INFO" in captured.err
    assert "WARN" in captured.err
    assert "ERROR" in captured.err


def test_init_creates_log_file(tmp_path, monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    import importlib
    import src.logger as logger_mod
    # Reset module state so init() re-runs cleanly
    logger_mod._log_file = None
    logger_mod._log_path = None

    log_path = logger_mod.init("test-session-123")
    assert log_path is not None
    assert "test-session-123" in log_path.name
    assert log_path.exists()


def test_init_log_file_written(tmp_path, monkeypatch):
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    import src.logger as logger_mod
    logger_mod._log_file = None
    logger_mod._log_path = None

    log_path = logger_mod.init("session-write-test")
    log = logger_mod.get_logger("filetest")
    log.info("file write check")

    content = log_path.read_text(encoding="utf-8")
    assert "file write check" in content


# ── Dev/prod separation (HARD RULE — see docs/issues/issue_002.md) ─────────────

def test_dev_init_never_writes_into_appdata(tmp_path, monkeypatch):
    """Non-frozen (dev) init() must open ONLY the repo-local log file —
    never %LOCALAPPDATA%\\com.alientech.alienvox\\logs, even though
    LOCALAPPDATA is set here (proving the dev path is skipped due to
    sys.frozen being unset, not because the env var happens to be
    invalid). Previously this wrote to both unconditionally."""
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    import src.logger as logger_mod
    logger_mod._log_files = []
    logger_mod._log_path = None

    logger_mod.init("dev-separation-test")

    appdata_logs = tmp_path / "com.alientech.alienvox" / "logs"
    assert not appdata_logs.exists()
    assert len(logger_mod._log_files) == 1


def test_frozen_init_writes_into_appdata_too(tmp_path, monkeypatch):
    """A frozen/installed build's init() must open BOTH the repo-local
    file (harmless if unwritable in a real install — best-effort) AND the
    AppData one."""
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    import src.logger as logger_mod
    logger_mod._log_files = []
    logger_mod._log_path = None

    logger_mod.init("frozen-separation-test")

    appdata_logs = tmp_path / "com.alientech.alienvox" / "logs"
    assert appdata_logs.exists()
    assert len(logger_mod._log_files) == 2
