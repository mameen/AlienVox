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
    do_get_catalog,
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
    engine_ids = set(result["engines"])
    assert {"kokoro", "piper", "supertonic3"} <= engine_ids
    detail_ids = {item["id"] for item in result["details"]}
    assert {"kokoro", "piper", "supertonic3"} <= detail_ids


def test_catalog_is_one_json_ready_inventory_with_trial_default_tradeoff():
    catalog = do_get_catalog()
    assert catalog["schema_version"] == 1
    assert catalog["default"] == {
        "engine": "kokoro",
        "voice": "af_heart",
        "device": "cpu",
    }
    assert catalog["trial_default"] is True
    assert catalog["tradeoff"]["benchmark_baseline_engine"] == "piper"
    assert catalog["tradeoff"]["voice"] == "en_US-amy-medium"
    assert catalog["tradeoff"]["warm_latency_seconds"] == 0.4214
    assert catalog["tradeoff"]["warm_cpu_seconds"] == 4.5
    piper = next(item for item in catalog["engines"] if item["id"] == "piper")
    assert piper["technology"] == "ONNX neural TTS"
    assert "en_GB-southern_english_female-low" in {v["id"] for v in piper["voices"]}
    southern_model = next(m for m in piper["models"] if m["id"] == "en_GB-southern_english_female-low")
    assert southern_model["approx_file_mb"] == 63
    assert any(item["id"] == "kokoro" for item in catalog["engines"])


def test_default_voice_listing_uses_current_quality_default():
    result = do_list_voices()
    assert result["engine"] == "kokoro"
    assert result["default_voice"] == "af_heart"
    assert "af_heart" in {voice["id"] for voice in result["voices"]}
    assert any(voice["is_default"] for voice in result["voices"])


def test_recommendations_include_top_voices_and_resource_priority():
    from tools import do_get_recommendations
    recs = do_get_recommendations()
    assert recs["priority"] == ["low latency", "low CPU", "low memory"]
    assert "F1" in recs["ml"][2]["voices"] and "F4" in recs["ml"][2]["voices"]
    piper = next(item for item in recs["ml"] if item["engine"] == "piper")
    assert set(piper["voices"]) == {
        "en_US-lessac-medium", "en_US-amy-medium", "en_US-ryan-high",
        "en_US-kathleen-low", "en_GB-southern_english_female-low",
        "en_GB-jenny_dioco-medium",
    }
    assert recs["sapi_preferred_voice"] == "MSTTS_V110_enUS_ZiraM"
    assert "not a quality verdict" in recs["sapi_note"]


def test_new_engine_rosters_are_available_without_loading_models():
    for engine, required in (("piper", {"en_US-ryan-high", "en_US-kathleen-low"}),
                             ("supertonic3", {"F1", "F4"})):
        result = do_list_voices(engine)
        assert {voice["id"] for voice in result["voices"]} >= required


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
    result = do_speak_text("Real MCP synthesis test, played by default.", voice="af_heart", engine="kokoro")
    assert "error" not in result
    assert result["device_requested"] == "cpu"  # confirms the CPU default
    assert result["played"] is True
    assert "path" not in result  # save=False by default -> no file written
    assert result["duration_s"] > 0


@requires_kokoro
def test_speak_text_save_true_writes_a_real_wav_file():
    result = do_speak_text("File-only synthesis test.", voice="af_heart", engine="kokoro", play=False, save=True)
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
        result = do_speak_text("volume reporting test", voice="af_heart", engine="kokoro", play=False, save=True)
        assert result["volume_used"] == 42
        Path(result["path"]).unlink()
    finally:
        do_set_volume(100)
