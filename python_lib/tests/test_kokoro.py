"""Real tests for alienvox_tts's Kokoro engine.

Per the anti-mocking philosophy this repo already follows for python_app
(see its .agents/SKILLS/testing/SKILL.md): these tests call real
synthesize(), not a mocked KPipeline. They skip (not fail) if kokoro/torch
aren't installed in the current environment — this library's dependencies
are optional to have installed just to browse/read the code, but any test
that actually runs must be real.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alienvox_tts import DEFAULT_VOICE, ENGINES, SpeakParams, list_voices, synthesize
from alienvox_tts.device import select_device
from alienvox_tts.engines.kokoro import KokoroEngine, _rate_to_speed
from alienvox_tts.volume import set_volume

try:
    import kokoro as _kokoro_pkg  # noqa: F401
    _KOKORO_INSTALLED = True
except ImportError:
    _KOKORO_INSTALLED = False

requires_kokoro = pytest.mark.skipif(
    not _KOKORO_INSTALLED,
    reason="kokoro package not installed — run `pip install -r python_lib/requirements.txt`",
)


# ── Pure logic — no model, no network, always runs ─────────────────────────

def test_default_voice_is_af_heart():
    assert DEFAULT_VOICE == "af_heart"


def test_kokoro_registered_as_default_engine():
    assert "kokoro" in ENGINES
    assert ENGINES["kokoro"] is KokoroEngine


def test_rate_to_speed_zero_is_natural_pace():
    assert _rate_to_speed(0) == 1.0


def test_rate_to_speed_max_is_double():
    assert _rate_to_speed(10) == 2.0


def test_rate_to_speed_min_is_half():
    assert _rate_to_speed(-10) == 0.5


def test_rate_to_speed_clamps_out_of_range():
    assert _rate_to_speed(999) == _rate_to_speed(10)
    assert _rate_to_speed(-999) == _rate_to_speed(-10)


def test_select_device_cpu_forced():
    assert select_device(prefer="cpu") == "cpu"


def test_select_device_returns_valid_string():
    assert select_device() in ("cpu", "cuda")


# ── Real synthesis — gated on kokoro being installed ────────────────────────

@requires_kokoro
def test_real_synthesis_produces_audio_with_correct_rate():
    audio, sr = synthesize("Hello, this is a real Kokoro test.", voice="af_heart")
    assert sr == 24_000
    assert isinstance(audio, np.ndarray)
    assert len(audio) > 100
    assert np.abs(audio).max() <= 1.0


@requires_kokoro
def test_real_synthesis_different_voice_produces_audio():
    audio, sr = synthesize("A British voice test.", voice="bm_george")
    assert sr == 24_000
    assert len(audio) > 100


@requires_kokoro
def test_synthesize_uses_persistent_volume_when_not_overridden():
    """synthesize()'s volume=None default must fall back to the current
    persistent level (set_volume()), not silently ignore it."""
    try:
        set_volume(20)
        quiet_audio, _ = synthesize("persistent volume test", voice="af_heart")
        set_volume(100)
        loud_audio, _ = synthesize("persistent volume test", voice="af_heart")
        # Same text/voice -> same underlying waveform shape scaled
        # differently; comparing peak amplitude is meaningful here (unlike
        # the cross-call VibeVoice nondeterminism issue documented
        # elsewhere in this project — Kokoro's CPU/GPU inference for
        # identical input is deterministic in practice for this check).
        assert np.abs(quiet_audio).max() < np.abs(loud_audio).max()
    finally:
        set_volume(100)  # don't leak state into other tests


@requires_kokoro
def test_synthesize_explicit_volume_overrides_persistent_level():
    try:
        set_volume(100)
        audio, _ = synthesize("explicit override test", voice="af_heart", volume=0)
        assert np.abs(audio).max() == pytest.approx(0.0, abs=1e-6)
    finally:
        set_volume(100)


@requires_kokoro
def test_real_synthesis_volume_zero_is_silent():
    audio, _ = synthesize("volume test", voice="af_heart", volume=0)
    assert np.abs(audio).max() == pytest.approx(0.0, abs=1e-6)


@requires_kokoro
def test_list_voices_returns_all_seven():
    voices = list_voices("kokoro")
    assert len(voices) == 7
    ids = {v.id for v in voices}
    assert "af_heart" in ids
    assert "bm_george" in ids


@requires_kokoro
def test_invalid_voice_falls_back_to_default():
    engine = KokoroEngine()
    result = engine.synthesize("fallback test", "not_a_real_voice", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == 24_000
    assert len(audio) > 100
