"""Real tests for alienvox_tts.volume — pure state logic, no model/network
involved, always runs (no skip conditions needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alienvox_tts.volume import get_volume, set_volume, volume_down, volume_up


def setup_function():
    # Reset module-level state before each test — these tests share a
    # single process-lifetime volume level by design (see volume.py's
    # docstring), so tests must not leak state into each other.
    set_volume(100)


def test_default_volume_is_100():
    assert get_volume() == 100


def test_set_volume_absolute():
    assert set_volume(40) == 40
    assert get_volume() == 40


def test_set_volume_clamps_above_100():
    assert set_volume(150) == 100


def test_set_volume_clamps_below_0():
    assert set_volume(-20) == 0


def test_volume_up_default_step_is_10():
    set_volume(50)
    assert volume_up() == 60
    assert get_volume() == 60


def test_volume_down_default_step_is_10():
    set_volume(50)
    assert volume_down() == 40
    assert get_volume() == 40


def test_volume_up_custom_step():
    set_volume(50)
    assert volume_up(step=25) == 75


def test_volume_up_clamps_at_100():
    set_volume(95)
    assert volume_up() == 100


def test_volume_down_clamps_at_0():
    set_volume(5)
    assert volume_down() == 0


def test_repeated_volume_up_reaches_100_from_zero():
    set_volume(0)
    for _ in range(10):
        volume_up()
    assert get_volume() == 100
