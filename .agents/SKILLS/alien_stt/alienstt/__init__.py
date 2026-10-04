#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""alienstt: local, offline speech-to-text, vendored inside the alien_stt skill.

Layers, bottom to top (each imports only from those above it in this list):

    base.py         data model + the `SttEngine` contract       (no heavy imports)
    device.py       CPU / CUDA selection
    audio.py        find, probe, decode, convert, split with ffmpeg
    postprocess.py  meaning-preserving clean-up, search folding
    formats.py      md / txt / srt / vtt / tsv / json writers, JSON loader
    trace.py        run id, JSONL events, summary
    engines/        concrete engines behind a registry (Whisper today)
    pipeline.py     composes the above: file in, `Transcript` out

Typical use::

    from alienstt import get_engine, transcribe_file, TranscribeOptions, write_outputs

    engine = get_engine("whisper", model="turbo")
    t = transcribe_file("meeting.mp3", engine, TranscribeOptions(language="en"))
    write_outputs(t, "out", "meeting", formats=["md", "srt", "json"])

Importing this package does not import torch or transformers; they load the
first time an engine actually transcribes, so the audio, formats and trace
layers are usable on a machine that only has ffmpeg.
"""
from __future__ import annotations

from .audio import (AUDIO_EXTENSIONS, MEDIA_EXTENSIONS, VIDEO_EXTENSIONS, AudioError, AudioInfo,
                    ToolNotFoundError, collect_inputs, convert, decode, plan_chunks, probe, quiet_ranges)
from .base import SAMPLE_RATE, Segment, SttEngine, Transcript, TranscribeOptions
from .device import cuda_available, select_device
from .engines import DEFAULT_ENGINE, DEFAULT_MODEL, ENGINES, MODEL_ALIASES, get_engine, resolve_model
from .formats import DEFAULT_FORMATS, FORMATS, load_transcript, parse_formats, render, write_outputs
from .pipeline import transcribe_audio, transcribe_file
from .postprocess import clean_segments, normalize_for_search, to_paragraphs
from .trace import RunLog, new_run_id

__all__ = [
    "AUDIO_EXTENSIONS", "AudioError", "AudioInfo", "DEFAULT_ENGINE", "DEFAULT_FORMATS", "DEFAULT_MODEL", "ENGINES",
    "FORMATS", "MEDIA_EXTENSIONS", "MODEL_ALIASES", "RunLog", "SAMPLE_RATE", "Segment", "SttEngine",
    "ToolNotFoundError", "TranscribeOptions", "Transcript", "VIDEO_EXTENSIONS", "clean_segments", "collect_inputs",
    "convert", "cuda_available", "decode", "get_engine", "load_transcript", "new_run_id", "normalize_for_search",
    "parse_formats", "plan_chunks", "probe", "quiet_ranges", "render", "resolve_model", "select_device",
    "to_paragraphs", "transcribe_audio", "transcribe_file", "write_outputs",
]
