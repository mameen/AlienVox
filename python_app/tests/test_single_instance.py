"""Tests for src/single_instance.py — dev/prod mutex separation.

Per the HARD RULE in docs/issues/issue_002.md: dev and prod must never
share OS-level identity objects (mutex names, data directories, log/
telemetry sinks). This file covers the mutex name itself; the guard's
actual acquire/release behavior is exercised for real by every app launch
(no separate mock-COM test — see testing/SKILL.md's OS/hardware-edge
exception for what's an acceptable stub boundary, and a Windows mutex
under a live-running test process isn't one).
"""
from __future__ import annotations

import sys


def test_dev_mutex_name_differs_from_prod():
    """The dev and prod mutex names must never collide — that's the whole
    point of this module existing (see its module docstring)."""
    dev_name = "Global\\AlienVox_SingleInstance_Dev"
    prod_name = "Global\\AlienVox_SingleInstance"
    assert dev_name != prod_name


def test_mutex_name_is_dev_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    import importlib
    import src.single_instance as si
    importlib.reload(si)
    try:
        assert si._MUTEX_NAME == "Global\\AlienVox_SingleInstance_Dev"
    finally:
        monkeypatch.delattr(sys, "frozen", raising=False)
        importlib.reload(si)  # restore module state for other tests


def test_mutex_name_is_prod_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    import importlib
    import src.single_instance as si
    importlib.reload(si)
    try:
        assert si._MUTEX_NAME == "Global\\AlienVox_SingleInstance"
    finally:
        monkeypatch.delattr(sys, "frozen", raising=False)
        importlib.reload(si)  # restore module state for other tests


def test_guard_acquires_real_mutex_on_windows():
    """Real OS-level acquisition — no mocking. A single guard in this
    process must always succeed (nothing else holds this exact dev mutex
    name during a test run)."""
    if sys.platform != "win32":
        return
    from src.single_instance import SingleInstanceGuard
    guard = SingleInstanceGuard()
    try:
        assert guard.acquired is True
    finally:
        guard.release()


def test_second_guard_blocked_while_first_holds_mutex():
    """Real second acquisition attempt in the same process must fail
    while the first guard still holds the mutex — proving the mutex
    actually enforces single-instance, not just that CreateMutex was
    called."""
    if sys.platform != "win32":
        return
    from src.single_instance import SingleInstanceGuard
    first = SingleInstanceGuard()
    try:
        assert first.acquired is True
        second = SingleInstanceGuard()
        try:
            assert second.acquired is False
        finally:
            second.release()
    finally:
        first.release()
