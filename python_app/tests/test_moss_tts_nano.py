from __future__ import annotations

import numpy as np

from src.engines.base import SpeakParams
from src.engines.moss_tts_nano_engine import (
    MossTtsNanoEngine,
    apply_volume,
    resolve_voice,
    validate_waveform,
)

from .conftest import requires_weights


def test_moss_voice_roster_and_resolution():
    voices = MossTtsNanoEngine().list_voices()
    assert len(voices) == 18
    assert {v.id for v in voices} >= {"Ava", "Adam", "Saki", "Junhao"}
    assert resolve_voice("Ava") == "Ava"
    assert resolve_voice("unknown") == "Ava"


def test_moss_volume_scales_multichannel_audio():
    audio = np.array([[1.0, -1.0], [0.5, -0.5]], dtype=np.float32)
    np.testing.assert_allclose(apply_volume(audio, 50), audio * 0.5)
    np.testing.assert_array_equal(apply_volume(audio, 0), np.zeros_like(audio))


def test_moss_waveform_validation_accepts_real_stereo_shape():
    waveform = np.ones((12_000, 2), dtype=np.float32)
    assert validate_waveform(waveform, 48_000) is waveform


def test_moss_waveform_validation_rejects_short_malformed_and_nonfinite_audio():
    import pytest

    with pytest.raises(ValueError, match="only 2 samples"):
        validate_waveform(np.ones((2, 2), dtype=np.float32), 48_000)
    with pytest.raises(ValueError, match="stereo"):
        validate_waveform(np.ones(12_000, dtype=np.float32), 48_000)
    invalid = np.ones((12_000, 2), dtype=np.float32)
    invalid[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        validate_waveform(invalid, 48_000)


def test_empty_text_and_ready_stop_lifecycle_do_not_load_runtime():
    engine = MossTtsNanoEngine()
    assert engine.synthesize("  ", "Ava", SpeakParams()) is None
    assert engine.wait_until_done(1)
    engine.speak("  ", "Ava", SpeakParams())
    engine.stop()
    assert engine.wait_until_done(1)
    engine._do_speak("", "Ava", SpeakParams())
    assert engine.wait_until_done(1)


@requires_weights("ml/moss_tts_nano")
def test_real_moss_onnx_cpu_synthesis():
    from src.control.app_controller import SAMPLE_TEXT

    audio, sample_rate = MossTtsNanoEngine().synthesize(
        SAMPLE_TEXT, "Ava", SpeakParams()
    )
    assert sample_rate == 48_000
    assert audio.ndim == 2 and audio.shape[1] == 2 and audio.shape[0] > sample_rate
    assert np.isfinite(audio).all()


@requires_weights("ml/moss_tts_nano")
def test_real_moss_second_voice_mute_is_silent():
    from src.control.app_controller import SAMPLE_TEXT

    audio, sample_rate = MossTtsNanoEngine().synthesize(
        SAMPLE_TEXT, "Adam", SpeakParams(volume=0)
    )
    assert sample_rate == 48_000 and audio.ndim == 2 and audio.shape[1] == 2
    assert np.count_nonzero(audio) == 0
