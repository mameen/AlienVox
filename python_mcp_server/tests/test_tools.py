"""Real tests for tools.py's domain logic — no MCP SDK needed here at all,
since tools.py has zero mcp imports (see its module docstring for why).
Skips gracefully if `kokoro` isn't installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import (  # noqa: E402
    do_get_volume,
    do_list_engines,
    do_list_voices,
    do_set_volume,
    do_speak_text,
    do_volume_down,
    do_volume_up,
)

try:
    import kokoro  # noqa: F401
    _KOKORO_INSTALLED = True
except ImportError:
    _KOKORO_INSTALLED = False

requires_kokoro = pytest.mark.skipif(not _KOKORO_INSTALLED, reason="kokoro package not installed")


def test_list_engines_includes_kokoro():
    result = do_list_engines()
    assert "kokoro" in result["engines"]


def test_list_voices_unknown_engine_returns_error():
    result = do_list_voices("not_a_real_engine")
    assert "error" in result


def test_speak_text_empty_text_returns_error():
    result = do_speak_text("   ")
    assert "error" in result


def test_speak_text_unknown_engine_returns_error():
    result = do_speak_text("hello", engine="not_a_real_engine")
    assert "error" in result


@requires_kokoro
def test_list_voices_real_returns_seven_kokoro_voices():
    result = do_list_voices("kokoro")
    assert result["engine"] == "kokoro"
    assert len(result["voices"]) == 7
    assert any(v["id"] == "af_heart" for v in result["voices"])


@requires_kokoro
def test_speak_text_default_plays_and_writes_no_file():
    """Default behavior (per real user feedback): play through local
    speakers, DON'T write a file nobody asked for. This actually plays
    real audio briefly — consistent with how python_app's own engine
    tests play real audio too (see e.g. test_kokoro.py in that repo)."""
    result = do_speak_text("Real MCP synthesis test, played by default.", voice="af_heart")
    assert "error" not in result
    assert result["device_requested"] == "cpu"  # confirms the CPU default
    assert result["played"] is True
    assert "path" not in result  # save=False by default -> no file written
    assert result["duration_s"] > 0


@requires_kokoro
def test_speak_text_save_true_writes_a_real_wav_file():
    result = do_speak_text("File-only synthesis test.", voice="af_heart", play=False, save=True)
    assert "error" not in result
    assert result["played"] is False
    wav_path = Path(result["path"])
    assert wav_path.exists()
    assert wav_path.stat().st_size > 0
    assert result["duration_s"] > 0
    wav_path.unlink()  # clean up — this test intentionally writes a real file


# ── Persistent volume ────────────────────────────────────────────────────────

def test_volume_absolute_and_relative():
    try:
        assert do_set_volume(50)["volume"] == 50
        assert do_get_volume()["volume"] == 50
        assert do_volume_up()["volume"] == 60
        assert do_volume_down(step=25)["volume"] == 35
    finally:
        do_set_volume(100)  # don't leak state into other tests


@requires_kokoro
def test_speak_text_volume_used_reflects_persistent_level_when_not_overridden():
    try:
        do_set_volume(42)
        result = do_speak_text("volume reporting test", voice="af_heart", play=False, save=True)
        assert result["volume_used"] == 42
        Path(result["path"]).unlink()
    finally:
        do_set_volume(100)
