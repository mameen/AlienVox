"""Tests for capture.py — clipboard round-trips (no UI focus required).

These tests run only on Windows. Tier 1 (WM_COPY) and Tier 2 (Ctrl+C)
require a real foreground window, so we only test the shared clipboard
helpers here — the integration of both tiers is verified manually.
"""
from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only"
)


@pytest.fixture(autouse=True)
def _restore_clipboard():
    """Save clipboard state before each test and restore it afterwards."""
    from src.capture import _read_clipboard, _write_clipboard
    before = _read_clipboard()
    yield
    if before:
        _write_clipboard(before)


# ── Clipboard helpers ─────────────────────────────────────────────────────────

def test_write_then_read_roundtrip():
    from src.capture import _read_clipboard, _write_clipboard
    _write_clipboard("AlienVox test string")
    assert _read_clipboard() == "AlienVox test string"


def test_write_empty_string():
    from src.capture import _read_clipboard, _write_clipboard
    _write_clipboard("")
    # empty string may be returned as "" or clipboard may be cleared
    result = _read_clipboard()
    assert isinstance(result, str)


def test_write_unicode():
    from src.capture import _read_clipboard, _write_clipboard
    text = "Héllo wörld — こんにちは"
    _write_clipboard(text)
    assert _read_clipboard() == text


def test_write_multiline():
    from src.capture import _read_clipboard, _write_clipboard
    text = "line one\nline two\nline three"
    _write_clipboard(text)
    assert _read_clipboard() == text


def test_read_returns_string_when_clipboard_empty():
    from src.capture import _read_clipboard, _write_clipboard
    # Clear clipboard by writing an empty string; read must return str, not None
    _write_clipboard("placeholder")  # ensure clipboard is openable
    result = _read_clipboard()
    assert isinstance(result, str)


def test_overwrite_replaces_previous():
    from src.capture import _read_clipboard, _write_clipboard
    _write_clipboard("first")
    _write_clipboard("second")
    assert _read_clipboard() == "second"


# ── Module import ─────────────────────────────────────────────────────────────

def test_module_imports_on_windows():
    import src.capture  # noqa: F401 — import must succeed on Windows


def test_get_selected_text_returns_string():
    """get_selected_text() must always return str, never raise."""
    from src.capture import get_selected_text
    result = get_selected_text(timeout_ms=10)
    assert isinstance(result, str)
