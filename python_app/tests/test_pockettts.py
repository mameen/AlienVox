"""Pure-logic tests for the optional Pocket TTS adapter."""
from __future__ import annotations

import numpy as np
import pytest

from src.engines.base import SpeakParams
from src.engines.pockettts_engine import PocketTTSEngine, apply_volume, resolve_voice

from .conftest import requires_weights


def test_resolve_voice_falls_back_to_default():
    assert resolve_voice("missing") == "alba"
    assert resolve_voice("marius") == "marius"


def test_apply_volume_scales_and_clamps():
    audio = np.array([1.0, -0.5], dtype=np.float32)
    np.testing.assert_allclose(apply_volume(audio, 50), [0.5, -0.25])
    np.testing.assert_allclose(apply_volume(audio, -1), [0.0, 0.0])
    np.testing.assert_allclose(apply_volume(audio, 150), audio)


def test_empty_text_and_ready_stop_lifecycle_do_not_load_model():
    engine = PocketTTSEngine()
    assert engine.synthesize("  ", "alba", SpeakParams()) is None
    assert engine.wait_until_done(1)
    engine.speak("  ", "alba", SpeakParams())
    engine.stop()
    assert engine.wait_until_done(1)
    engine._do_speak("", "alba", SpeakParams())
    assert engine.wait_until_done(1)


@requires_weights("ml/pockettts")
def test_real_pocket_synthesis_is_finite_audio():
    from src.control.app_controller import SAMPLE_TEXT

    result = PocketTTSEngine().synthesize(SAMPLE_TEXT, "alba", SpeakParams())
    assert result is not None
    audio, sample_rate = result
    assert sample_rate > 0 and audio.ndim == 1 and audio.size > sample_rate // 2
    assert np.isfinite(audio).all()


@requires_weights("ml/pockettts")
@pytest.mark.parametrize("voice_id", ["alba", "marius", "unknown"])
def test_real_pocket_voice_choices_and_mute(voice_id):
    from src.control.app_controller import SAMPLE_TEXT

    audio, rate = PocketTTSEngine().synthesize(
        SAMPLE_TEXT, voice_id, SpeakParams(volume=0)
    )
    assert rate == 24_000 and audio.size > rate // 2
    assert np.isfinite(audio).all() and np.count_nonzero(audio) == 0
