"""Tests for DiaEngine.

Per .agents/SKILLS/highlevel_design/SKILL.md's anti-mocking testing
philosophy: speaker-tag prepending logic was extracted into a pure
build_tagged_text() function (dia_engine.py) so it can be tested directly
with zero mocking — no model access needed at all for that class of test.

Real generate() calls are slow even with the model cached (~20-70s each,
observed during perf runs), so real-synthesis tests below are consolidated
into the minimum number of real calls that still cover: valid audio output,
correct sample rate, and volume scaling — all gated by @requires_weights.

One test (stereo-to-mono conversion) still stubs generate()'s return value:
Dia is a mono-only model per its own docs, so there's no way to get it to
produce genuinely stereo output for a real test — this exercises our
defensive shape-handling branch for an output shape Dia itself won't
produce, not simulated "normal" Dia behavior.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.dia_engine import (
    _DEFAULT_VOICE,
    _SAMPLE_RATE,
    _TAG,
    _VALID_VOICE_IDS,
    DiaEngine,
    build_tagged_text,
)

from .conftest import requires_weights

requires_dia_weights = requires_weights("ml/dia")

# ── Voice roster ──────────────────────────────────────────────────────────────

def test_valid_voice_ids_non_empty():
    assert len(_VALID_VOICE_IDS) > 0


def test_known_voices_in_roster():
    assert "s1" in _VALID_VOICE_IDS
    assert "s2" in _VALID_VOICE_IDS


def test_default_voice_in_roster():
    assert _DEFAULT_VOICE in _VALID_VOICE_IDS


def test_list_voices_returns_all():
    engine = DiaEngine()
    ids = {v.id for v in engine.list_voices()}
    assert ids == _VALID_VOICE_IDS


def test_kokoro_voices_not_in_roster():
    for vid in ("af_heart", "default", "en_US-amy-medium"):
        assert vid not in _VALID_VOICE_IDS


# ── Speaker tag mapping ───────────────────────────────────────────────────────

@pytest.mark.parametrize("voice_id,expected_tag", [
    ("s1", "[S1]"),
    ("s2", "[S2]"),
])
def test_speaker_tag_mapping(voice_id, expected_tag):
    assert _TAG[voice_id] == expected_tag


# ── build_tagged_text: pure logic, no model/mocking needed ───────────────────

def test_invalid_voice_falls_back_to_default_tag():
    assert build_tagged_text("hello", "bad_voice").startswith(_TAG[_DEFAULT_VOICE])


def test_s1_tag_prepended():
    assert build_tagged_text("hello", "s1") == "[S1] hello"


def test_s2_tag_prepended():
    assert build_tagged_text("hello", "s2") == "[S2] hello"


def test_pre_tagged_text_passes_through_unchanged():
    """Text that already contains speaker tags is not re-wrapped."""
    input_text = "[S1] Hello. [S2] World."
    assert build_tagged_text(input_text, "s1") == input_text


def test_text_is_stripped_before_tagging():
    assert build_tagged_text("  hello  ", "s1") == "[S1] hello"


# ── Real synthesis ─────────────────────────────────────────────────────────────

@requires_dia_weights
def test_real_synthesis_produces_audio_with_correct_rate():
    engine = DiaEngine()
    result = engine.synthesize("Hello, this is a real Dia test.", "s1", SpeakParams())
    assert result is not None
    audio, sr = result
    assert sr == _SAMPLE_RATE
    assert len(audio) > 100
    assert audio.dtype == np.float32
    assert np.abs(audio).max() <= 1.0


@requires_dia_weights
def test_real_synthesis_volume_scaling():
    """Dia's generate() isn't seeded/deterministic — two independent real
    calls produce genuinely different waveforms, so comparing their peaks
    directly isn't a valid volume test. Instead: generate once for real,
    then re-run _synthesize_array with the real model's generate() wrapped
    to return that same real array again, isolating volume math from
    generation randomness while still exercising the real model once."""
    engine = DiaEngine()
    model = engine._get_model()  # real model, loaded once

    full = engine.synthesize("volume scaling test", "s1", SpeakParams(volume=100))
    assert full is not None
    full_audio, _ = full
    full_peak = np.abs(full_audio).max()
    assert full_peak > 0

    # Reconstruct the pre-scaling raw array (full_audio was already scaled
    # by volume=100/100=1.0, so it equals the raw array here) and replay it
    # through generate() to test volume=50 scaling against the *same*
    # real content.
    with patch.object(model, "generate", return_value=full_audio.copy()):
        half = engine.synthesize("volume scaling test", "s1", SpeakParams(volume=50))
    assert half is not None
    half_audio, _ = half
    half_peak = np.abs(half_audio).max()
    assert abs(half_peak - full_peak * 0.5) < full_peak * 0.05


def test_speak_empty_text_does_nothing():
    """No mocking needed — empty text must short-circuit before ever
    touching _get_model(), real or otherwise."""
    engine = DiaEngine()
    with patch("src.engines.dia_engine.play_audio") as mock_play:
        engine.speak("", "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=1_000)
    mock_play.assert_not_called()


def test_stereo_output_converted_to_mono():
    """Dia is documented as mono-only, so real output can't exercise this
    branch — stubs generate()'s return shape specifically to test our
    defensive stereo->mono averaging, not Dia's normal behavior."""
    stereo = np.ones((2, 4410), dtype=np.float32)
    mock_model = MagicMock()
    mock_model.generate.return_value = stereo
    engine = DiaEngine()
    DiaEngine._model = mock_model
    played = []

    with patch("src.engines.dia_engine.play_audio",
               side_effect=lambda a, r: played.append(a)):
        engine.speak("stereo test", "s1", SpeakParams())
        engine.wait_until_done(timeout_ms=5_000)

    assert len(played) == 1
    assert played[0].ndim == 1


# ── stop / wait_until_done ───────────────────────────────────────────────────

def test_stop_sets_done():
    engine = DiaEngine()
    engine._done.clear()
    engine.stop()
    assert engine._done.is_set()


def test_stop_sets_stop_requested():
    engine = DiaEngine()
    engine.stop()
    assert engine._stop_requested.is_set()


def test_wait_until_done_returns_true_when_set():
    engine = DiaEngine()
    engine._done.set()
    assert engine.wait_until_done(timeout_ms=100) is True


def test_wait_until_done_returns_false_on_timeout():
    engine = DiaEngine()
    engine._done.clear()
    assert engine.wait_until_done(timeout_ms=50) is False
