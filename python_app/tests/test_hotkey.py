"""Tests for hotkey.enhanced_variant_of — the "Play Enhanced" global
hotkey is always the primary hotkey plus Shift, derived rather than a
separate configurable field."""
from __future__ import annotations

from src.control.hotkey import enhanced_variant_of


def test_enhanced_variant_of_default_hotkey():
    assert enhanced_variant_of("<alt>+<esc>") == "<shift>+<alt>+<esc>"


def test_enhanced_variant_works_for_arbitrary_combos():
    assert enhanced_variant_of("<ctrl>+<alt>+h") == "<shift>+<ctrl>+<alt>+h"
