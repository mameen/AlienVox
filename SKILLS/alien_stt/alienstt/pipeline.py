#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The transcription pipeline: file in, `Transcript` out.

This is the one place that composes the other layers, and it is deliberately
short. Each step is a call into a module that owns that job:

    decode (audio.py) -> [detect language (engine)] -> plan chunks (audio.py)
      -> transcribe each chunk (engine) -> shift + clean (postprocess.py)
      -> Transcript (base.py)

The CLI, the tests and any library caller all go through `transcribe_file` or
`transcribe_audio`, so there is one behaviour, not three.

Language handling
-----------------
If the caller did not name a language, the pipeline detects it *once* from the
start of the file and then passes that language to every chunk. Detecting per
chunk would let a single noisy chunk flip a monolingual file into the wrong
language, and the resulting transcript would switch scripts mid-way. The
detected language and its probability are recorded; a low probability adds a
warning, because a wrong guess is the most common cause of garbage output.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Optional

import numpy as np

from . import audio as audio_mod
from .base import SAMPLE_RATE, ProgressFn, Segment, SttEngine, Transcript, TranscribeOptions
from .postprocess import clean_segments, drop_segments_in_silence, shift
from .trace import datetime_stamp

#: Below this detection probability the transcript carries a warning.
LOW_LANGUAGE_CONFIDENCE = 0.6


def transcribe_audio(
    samples: np.ndarray,
    engine: SttEngine,
    options: Optional[TranscribeOptions] = None,
    *,
    source: str = "audio",
    on_progress: Optional[ProgressFn] = None,
) -> Transcript:
    """Transcribe already-decoded 16 kHz mono float32 samples.

    Use this when the audio is already in memory (a microphone buffer, a slice
    you cut yourself). For files use `transcribe_file`.
    """
    options = options or TranscribeOptions()
    duration = samples.size / SAMPLE_RATE
    warnings: list[str] = []
    language, probability = options.language, None

    if language is None:
        language, probability = engine.detect_language(samples)
        if language is None:
            warnings.append("language could not be detected; the engine chose one")
        elif probability is not None and probability < LOW_LANGUAGE_CONFIDENCE:
            warnings.append(
                f"language detected as {language!r} with only {probability:.0%} confidence; "
                "pass an explicit language if it is wrong")
        options = dataclasses.replace(options, language=language)

    quiet = audio_mod.quiet_ranges(samples, SAMPLE_RATE) if 0 < options.chunk_seconds < duration else []
    pieces = audio_mod.plan_chunks(duration, quiet, options.chunk_seconds)

    segments: list[Segment] = []
    for i, (a, b) in enumerate(pieces):
        if on_progress:
            on_progress(i / len(pieces), f"chunk {i + 1}/{len(pieces)}")
        piece = samples[int(a * SAMPLE_RATE): int(b * SAMPLE_RATE)]
        segments += shift(engine.transcribe(piece, options), a)
    if on_progress:
        on_progress(1.0, "done")

    if options.silence_guard_db is not None and segments:
        silent = audio_mod.quiet_ranges(samples, SAMPLE_RATE, threshold_db=options.silence_guard_db, min_silence=0.5)
        segments, dropped = drop_segments_in_silence(segments, silent)
        if dropped:
            warnings.append(f"dropped {dropped} segment(s) written over silence")
    segments = clean_segments(segments)
    if not segments:
        warnings.append("no speech was detected")
    if len(pieces) > 1:
        warnings.append(f"processed in {len(pieces)} chunks; boundaries sit in quiet gaps but check them")

    return Transcript(
        source=source, segments=segments, duration=round(duration, 2),
        language=language, language_probability=None if probability is None else round(probability, 3),
        model=engine.model_name, engine=engine.name, device=engine.device_name,
        task=options.task, created=datetime_stamp(), warnings=warnings,
    )


def transcribe_file(
    path: str | os.PathLike,
    engine: SttEngine,
    options: Optional[TranscribeOptions] = None,
    *,
    on_progress: Optional[ProgressFn] = None,
) -> Transcript:
    """Decode a media file and transcribe it.

    Any format ffmpeg reads is accepted (see `alienstt.audio.MEDIA_EXTENSIONS`).
    Raises `alienstt.audio.AudioError` if the file cannot be decoded.
    """
    samples = audio_mod.decode(path)
    return transcribe_audio(samples, engine, options, source=os.path.basename(str(path)), on_progress=on_progress)
