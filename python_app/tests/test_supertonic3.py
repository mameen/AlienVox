from __future__ import annotations

import numpy as np

from src.engines.base import SpeakParams
from src.engines.supertonic3_engine import Supertonic3Engine, apply_volume

from .conftest import requires_weights


def test_supertonic_voice_list_and_volume():
    engine = Supertonic3Engine()
    assert len(engine.list_voices()) == 10
    np.testing.assert_allclose(apply_volume(np.array([1.0, -1.0]), 50), [0.5, -0.5])


def test_empty_text_and_ready_stop_lifecycle_do_not_load_model():
    engine = Supertonic3Engine()
    assert engine.synthesize("  ", "M1", SpeakParams()) is None
    assert engine.wait_until_done(1)
    engine.speak("  ", "M1", SpeakParams())
    assert engine.wait_until_done(1_000)
    engine.stop()
    assert engine.wait_until_done(1)
    engine._do_speak("", "M1", SpeakParams())
    assert engine.wait_until_done(1)


@requires_weights("ml/supertonic3")
def test_real_supertonic_synthesis_is_finite_audio():
    from src.control.app_controller import SAMPLE_TEXT

    audio, sample_rate = Supertonic3Engine().synthesize(SAMPLE_TEXT, "M1", SpeakParams())
    assert sample_rate > 0 and audio.ndim == 1 and audio.size > sample_rate // 2
    assert np.isfinite(audio).all()


@requires_weights("ml/supertonic3")
def test_real_supertonic_other_voice_and_mute():
    from src.control.app_controller import SAMPLE_TEXT

    audio, sample_rate = Supertonic3Engine().synthesize(
        SAMPLE_TEXT, "F1", SpeakParams(volume=0)
    )
    assert sample_rate == 44_100 and audio.size > sample_rate // 2
    assert np.isfinite(audio).all() and np.count_nonzero(audio) == 0
