#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Meaning-preserving clean-up of segment lists, plus text normalisation for search.

The rule for this module is the same one the text-to-speech skill follows for
enhancement: **it may remove noise, never change what was said.** Every
function here either drops something that is not speech (an empty segment, a
loop the model got stuck in) or re-arranges segments that already exist
(shifting times, grouping into paragraphs). Nothing rewrites words, fixes
spelling or "improves" a sentence; that judgement belongs to a person who
listened.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

from .base import Segment

# Characters that vary between writers of the same word and should not stop a
# search from matching: the Arabic tatweel (a purely typographic stretch).
_TATWEEL = "ـ"
_WS = re.compile(r"\s+")


def clean_segments(segments: Iterable[Segment], max_repeat: int = 2) -> list[Segment]:
    """Remove empty segments and runaway repetition; make times monotonic.

    Whisper-family models occasionally get stuck and emit the same line over
    and over ("Thank you. Thank you. Thank you."), usually over music or
    near-silence. A run of identical consecutive segments longer than
    `max_repeat` is cut down to `max_repeat`. Two are kept, not one, because a
    speaker genuinely repeating a phrase once is normal.

    Time repair: every segment gets ``end >= start``, and a segment never
    starts before the previous one began. Engines should already guarantee
    this; the repair is cheap insurance because subtitle players reject
    out-of-order cues.
    """
    out: list[Segment] = []
    run = 0
    last_key = None
    for seg in segments:
        text = _WS.sub(" ", seg.text).strip()
        if not text:
            continue
        key = text.casefold()
        run = run + 1 if key == last_key else 1
        last_key = key
        if run > max_repeat:
            continue
        start = max(seg.start, out[-1].start if out else 0.0)
        out.append(Segment(start, max(seg.end, start), text))
    return out


def drop_segments_in_silence(
    segments: Iterable[Segment],
    quiet: Sequence[tuple[float, float]],
    min_overlap: float = 0.9,
) -> tuple[list[Segment], int]:
    """Remove segments that lie almost entirely inside the given quiet ranges.

    Returns ``(kept, dropped_count)``. This is the guard against recognisers
    inventing text over silence: a segment is dropped only when at least
    `min_overlap` of its duration falls inside `quiet`, i.e. the audio under it
    was effectively silent, so there was nothing to transcribe. Segments with
    speech under them are never touched.
    """
    kept: list[Segment] = []
    dropped = 0
    for s in segments:
        length = max(s.end - s.start, 1e-6)
        covered = sum(max(0.0, min(s.end, b) - max(s.start, a)) for a, b in quiet)
        if covered / length >= min_overlap:
            dropped += 1
        else:
            kept.append(s)
    return kept, dropped


def shift(segments: Iterable[Segment], offset: float) -> list[Segment]:
    """Return copies of `segments` moved `offset` seconds later.

    Used when a long file is transcribed in pieces: each piece's times are
    relative to the piece, and adding the piece's start makes them relative to
    the whole file.
    """
    return [Segment(s.start + offset, s.end + offset, s.text) for s in segments]


def to_paragraphs(segments: Iterable[Segment], gap: float = 1.5) -> list[str]:
    """Group segments into paragraphs, starting a new one after a pause.

    `gap` is the silence in seconds between one segment's end and the next
    one's start that counts as a paragraph break. This is presentation only:
    the text is joined with spaces, nothing else is touched.
    """
    paragraphs: list[list[str]] = []
    prev_end = None
    for s in segments:
        if prev_end is None or s.start - prev_end > gap:
            paragraphs.append([])
        paragraphs[-1].append(s.text)
        prev_end = s.end
    return [" ".join(p) for p in paragraphs]


def normalize_for_search(text: str) -> str:
    """Fold text so a search matches across case, accents and optional marks.

    Steps: Unicode NFKD, drop combining marks (accents in Latin scripts,
    vowel marks such as Arabic tashkeel and Hebrew niqqud), drop the Arabic
    tatweel, case-fold, collapse whitespace. The result is for *comparison
    only*; never write it back into a transcript.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c) and c != _TATWEEL)
    return _WS.sub(" ", stripped.casefold()).strip()
