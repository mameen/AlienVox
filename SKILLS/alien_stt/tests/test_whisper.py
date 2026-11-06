"""Real Whisper tests: they load the model and transcribe real speech. Skipped when the model is not cached."""
from __future__ import annotations

import numpy as np
import pytest

from alienstt import TranscribeOptions, get_engine, transcribe_audio, transcribe_file
from alienstt import audio as A
from conftest import SAMPLE_WORDS, requires_model


def _says(text: str):
    low = text.lower()
    return [w for w in SAMPLE_WORDS if w in low]


def test_unknown_engine_names_the_choices():
    with pytest.raises(KeyError, match="whisper"):
        get_engine("nope")


@requires_model
def test_transcribes_real_speech_from_wav(engine, sample_wav):
    t = transcribe_file(sample_wav, engine, TranscribeOptions(language="en"))
    assert _says(t.text) == list(SAMPLE_WORDS), t.text
    assert t.language == "en" and t.model.endswith("whisper-large-v3-turbo") and t.engine == "whisper"
    assert t.created.isdigit() and len(t.created) == 14
    assert 0 <= t.segments[0].start < t.segments[-1].end <= t.duration + 0.5


@requires_model
def test_same_words_from_mp3(engine, sample_wav, tmp_path):
    mp3 = A.convert(sample_wav, tmp_path / "s.mp3")
    t = transcribe_file(mp3, engine, TranscribeOptions(language="en"))
    assert _says(t.text) == list(SAMPLE_WORDS), t.text


@requires_model
def test_language_is_detected_when_not_given(engine, sample_wav):
    t = transcribe_file(sample_wav, engine)
    assert t.language == "en"
    assert t.language_probability is not None and t.language_probability > 0.9


@requires_model
def test_language_scores_sorted_and_normalised(engine, sample_wav):
    scores = engine.language_scores(A.decode(sample_wav), top=5)
    assert scores[0][0] == "en"
    assert [p for _, p in scores] == sorted((p for _, p in scores), reverse=True)
    assert 0.9 < scores[0][1] <= 1.0


@requires_model
def test_silence_yields_no_text_and_a_warning(engine):
    t = transcribe_audio(np.zeros(16000 * 8, dtype="float32"), engine, TranscribeOptions(language="en"))
    assert t.segments == [] and any("no speech" in w for w in t.warnings)


@requires_model
def test_long_file_is_chunked_in_gaps_and_timeline_is_global(engine, gapped_wav):
    # chunk_seconds=10 forces the pipeline to split ~21 s of audio at the 3 s gaps.
    t = transcribe_file(gapped_wav, engine, TranscribeOptions(language="en", chunk_seconds=10))
    assert any("chunks" in w for w in t.warnings)
    starts = [s.start for s in t.segments]
    assert starts == sorted(starts) and starts[-1] > 10               # later chunks carry global times
    assert sum("welcome" in s.text.lower() for s in t.segments) == 3  # all three utterances survive the cuts


@requires_model
def test_prompt_option_is_accepted(engine, sample_wav):
    t = transcribe_file(sample_wav, engine, TranscribeOptions(language="en", prompt="AlienVox, TTS"))
    assert "alienvox" in t.text.lower().replace(" ", "")
