#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Data model and engine contract shared by every part of alienstt.

Two ideas live here and nothing else:

1. **The data that flows through the library** (`Segment`, `Transcript`,
   `TranscribeOptions`). Every writer, post-processor and CLI tool speaks
   these types, so a transcript produced by one engine can be re-rendered,
   searched or merged by tools that never heard of that engine.

2. **The contract an engine must satisfy** (`SttEngine`). The rest of the
   library never imports a concrete engine; it asks the registry in
   `alienstt.engines` for one by name and uses only the methods below. That
   is what makes adding a second engine (say `faster-whisper`) a one-file
   change instead of a rewrite.

Design rules, and why they exist
--------------------------------
* **Plain dataclasses, no behaviour that needs a model.** A `Transcript` must
  be constructible, serialisable and testable on a machine with no GPU, no
  torch and no model weights. Only `SttEngine` implementations touch those.
* **Times are float seconds from the start of the source file.** Not frames,
  not milliseconds, not "chunk-relative". Chunked processing adds the chunk
  offset before a `Segment` ever leaves the engine layer, so callers never
  have to know whether a file was processed whole or in pieces.
* **Unknown is `None`, never a made-up default.** A language that was not
  detected is `None`, not `"en"`. A probability that the backend did not report
  is `None`, not `0.0`. Downstream code can then tell "measured zero" from
  "not measured", which matters when a human decides how far to trust a draft.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import numpy as np

# Whisper-family models are trained on 16 kHz mono audio. Every engine in this
# library consumes that format, so the audio layer decodes to it once and the
# engines never resample. Kept here (not in audio.py) because it is part of
# the engine contract, not an audio-I/O detail.
SAMPLE_RATE = 16000


@dataclass
class Segment:
    """One timed piece of transcribed text.

    `start` and `end` are seconds from the beginning of the source file.
    `text` is stripped of leading/trailing whitespace by the engine layer, so
    writers can join segments without re-cleaning.
    """

    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly form; rounded so files diff cleanly between runs."""
        return {"start": round(self.start, 2), "end": round(self.end, 2), "text": self.text}


@dataclass
class TranscribeOptions:
    """Every knob a caller can turn, in one place.

    The CLI maps flags onto these fields one-to-one, and the library API takes
    the same object, so "what can I configure?" has exactly one answer.

    Fields
    ------
    language:
        ISO code such as ``"ar"`` or ``"en"``. ``None`` lets the engine detect
        it. Naming the language is almost always more accurate: detection
        looks at the first 30 s only and is least reliable on short clips,
        accented speech and mixed-language audio.
    task:
        ``"transcribe"`` writes what was said in the spoken language;
        ``"translate"`` writes English text from any spoken language.
    beam_size:
        Beam-search width. ``1`` is greedy (fastest). Larger values are
        slower and a little more accurate on hard audio.
    temperature:
        Fallback ladder. Decoding starts at the first value; when a window
        fails the quality checks below, the next value is tried. A ladder is
        what lets the engine recover from a stuck repetition loop.
    compression_ratio_threshold:
        A window whose text compresses better than this is treated as a
        repetition loop and re-decoded. Lower = stricter.
    logprob_threshold:
        A window whose average log-probability is below this is treated as
        low confidence and re-decoded.
    no_speech_threshold:
        A window whose "no speech" probability is above this (and whose
        confidence is also low) is dropped as silence rather than transcribed.
        This is the main guard against invented text over silence or music.
    prompt:
        Optional text shown to the model as if it were the preceding sentence.
        Use it to bias spelling of names and domain terms ("Kubernetes",
        "Dr. Aisha Rahman"). It biases; it does not guarantee. A long or
        irrelevant prompt can make output worse.
    chunk_seconds:
        Files longer than this are processed in silence-aligned pieces so
        memory stays bounded. ``0`` disables chunking. Chunk boundaries are
        placed in quiet gaps, so words are not cut in half.
    silence_guard_db:
        Whisper-family models sometimes write a confident phrase ("Thank you.")
        over true silence, and their own no-speech check does not always catch
        it. After decoding, any segment that lies (at least 90%) inside audio
        quieter than this many dBFS is dropped, and a warning says how many.
        The default, -55 dBFS, is far below any speech, so it only removes
        material that was effectively silent. ``None`` disables the guard.
    word_timestamps:
        Reserved for engines that support it; ignored by those that do not.
    """

    language: Optional[str] = None
    task: str = "transcribe"
    beam_size: int = 1
    temperature: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    compression_ratio_threshold: float = 1.35
    logprob_threshold: float = -1.0
    no_speech_threshold: float = 0.6
    prompt: Optional[str] = None
    chunk_seconds: float = 1800.0
    silence_guard_db: Optional[float] = -55.0
    word_timestamps: bool = False


@dataclass
class Transcript:
    """A finished transcription plus the provenance needed to trust it.

    The provenance fields (`model`, `engine`, `device`, `created`, `source`,
    `task`, `language`) are what a reader needs to judge a draft later: which
    model produced it, on what device, when, from which file. A transcript
    without provenance cannot be reproduced and should not be quoted.
    `created` is a DATETIME STAMP (``YYYYMMDDHHmmss``, Pacific time).
    """

    source: str
    segments: list[Segment]
    duration: float
    language: Optional[str] = None
    language_probability: Optional[float] = None
    model: str = ""
    engine: str = ""
    device: str = ""
    task: str = "transcribe"
    created: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """All segment text joined with single spaces."""
        return " ".join(s.text for s in self.segments if s.text).strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialisable form. `from_dict` is its exact inverse."""
        data = asdict(self)
        data["segments"] = [s.to_dict() for s in self.segments]
        data["text"] = self.text
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transcript":
        """Rebuild a transcript from `to_dict()` output (or a JSON file of it).

        Unknown keys are ignored so a transcript written by a newer version
        still loads in an older one.
        """
        known = {k: data[k] for k in (
            "source", "duration", "language", "language_probability", "model",
            "engine", "device", "task", "created", "warnings") if k in data}
        segs = [Segment(float(s["start"]), float(s["end"]), str(s["text"])) for s in data.get("segments", [])]
        known.setdefault("source", "")
        known.setdefault("duration", segs[-1].end if segs else 0.0)
        return cls(segments=segs, **known)


# Called by the pipeline as work proceeds: (fraction_done_0_to_1, message).
ProgressFn = Callable[[float, str], None]


class SttEngine(ABC):
    """What every speech-to-text backend must provide.

    Two methods are mandatory. Everything else (loading, caching, device
    placement) is the engine's own business and happens lazily on first use,
    so constructing an engine is cheap and failing on a missing model happens
    at the moment of real work, with a real error, not at import time.

    Engines receive already-decoded audio (16 kHz mono float32 numpy). They
    never read files, never call ffmpeg and never write output; those jobs
    belong to the audio and formats layers. That separation is what lets the
    same engine serve the CLI, a library caller and the tests identically.
    """

    #: Registry key, for example ``"whisper"``.
    name: str = ""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, options: TranscribeOptions) -> list[Segment]:
        """Return timed segments for `audio` (16 kHz mono float32).

        Times must be relative to the start of `audio`; the pipeline shifts
        them when it processes a long file in chunks. An engine must return
        an empty list for silence rather than inventing text.
        """

    @abstractmethod
    def detect_language(self, audio: np.ndarray) -> tuple[Optional[str], Optional[float]]:
        """Return ``(language_code, probability)`` for the audio, or
        ``(None, None)`` if the engine cannot tell."""

    def language_scores(self, audio: np.ndarray, top: int = 5) -> list[tuple[str, float]]:
        """Return up to `top` ``(language_code, probability)`` pairs, best first.

        Optional: the default returns an empty list, meaning "this engine only
        offers a single best guess through `detect_language`".
        """
        return []

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the loaded model, recorded in transcript provenance."""

    @property
    @abstractmethod
    def device_name(self) -> str:
        """Device actually used (``"cuda"`` or ``"cpu"``), recorded in provenance."""
