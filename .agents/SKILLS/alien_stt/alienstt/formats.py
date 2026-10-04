#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Render a `Transcript` as Markdown, plain text, SRT, WebVTT, TSV or JSON, and read JSON back.

One transcript, many views. The JSON file is the lossless one: it carries every
segment and the provenance block, and `load_transcript()` rebuilds a
`Transcript` from it. That makes JSON the right thing to keep and the others
disposable renderings of it. `scripts/render_transcript.py` regenerates any
format from a saved JSON without touching the model again.

Format guide (see also references/output-formats.md)
----------------------------------------------------
md    Header with provenance, then ``[mm:ss] text`` lines. For people to read and
      to check against the audio. Carries the "automatic draft" notice.
txt   Text only, one paragraph per pause. For pasting and for downstream tools.
srt   Numbered cues with ``HH:MM:SS,mmm`` times. For video players and editors.
vtt   WebVTT: like SRT with ``.`` before milliseconds. For browsers and the web.
tsv   ``start<TAB>end<TAB>text`` with a header row. For spreadsheets and scripts.
json  Everything. For re-rendering, merging and search.

Output file names are ``<stem>.transcript.md``, ``<stem>.txt``, ``<stem>.srt``,
``<stem>.vtt``, ``<stem>.tsv``, ``<stem>.json``. The ``.transcript.md`` double
suffix keeps the Markdown from colliding with a hand-written ``<stem>.md``.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Iterable, Optional

from .base import Transcript
from .postprocess import to_paragraphs

#: Every format name this module can write, in a stable order.
FORMATS = ("md", "txt", "srt", "vtt", "tsv", "json")

#: Default selection when a caller does not choose: readable plus plain.
DEFAULT_FORMATS = ("md", "txt")

_SUFFIX = {"md": ".transcript.md", "txt": ".txt", "srt": ".srt", "vtt": ".vtt", "tsv": ".tsv", "json": ".json"}

DRAFT_NOTICE = (
    "An automatic draft, not checked by a person. Speech recognition can mishear names, numbers, "
    "technical terms and unclear audio; check anything that matters against the recording."
)


def parse_formats(spec: str) -> list[str]:
    """Turn ``"md,srt"`` (or ``"all"``) into a validated list of format names.

    Raises `ValueError` naming the unknown format, so a typo fails before any
    model work starts rather than after an hour of transcription.
    """
    if spec.strip().lower() == "all":
        return list(FORMATS)
    names = [p.strip().lower() for p in spec.split(",") if p.strip()]
    bad = [n for n in names if n not in FORMATS]
    if bad:
        raise ValueError(f"unknown format(s): {', '.join(bad)}; choose from {', '.join(FORMATS)} or 'all'")
    if not names:
        raise ValueError("no formats given")
    return names


def clock(seconds: float, *, millis: bool = False, dot: bool = False) -> str:
    """Format seconds as ``mm:ss`` / ``h:mm:ss``, or ``HH:MM:SS,mmm`` with `millis`.

    `dot=True` uses ``.`` before the milliseconds (WebVTT) instead of ``,`` (SRT).
    """
    seconds = max(0.0, float(seconds or 0))
    total_ms = int(round(seconds * 1000)) if millis else int(seconds) * 1000   # round once, then split: no carry bugs
    whole, ms = divmod(total_ms, 1000)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    if millis:
        return f"{h:02d}:{m:02d}:{s:02d}{'.' if dot else ','}{ms:03d}"
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _date(stamp: str) -> str:
    """``20261003190525`` -> ``2026-10-03`` (a DATETIME STAMP's day); anything else passes through."""
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 and stamp[:8].isdigit() else stamp


def render_md(t: Transcript, tool: str = "alienstt") -> str:
    lang = t.language or "auto-detected"
    if t.language and t.language_probability is not None:
        lang += f" ({t.language_probability:.0%} confidence)"
    if t.task == "translate":
        lang += ", translated to English"
    lines = [
        f"# Transcript: {t.source}", "",
        f"- Source: `{t.source}`",
        f"- Model: `{t.model}` ({t.engine}, {t.device})",
        f"- Language: {lang}",
        f"- Length: {clock(t.duration)}",
        f"- Made: {_date(t.created)} by {tool}",
        f"- Note: {DRAFT_NOTICE}",
    ]
    for w in t.warnings:
        lines.append(f"- Warning: {w}")
    lines.append("")
    for s in t.segments:
        lines += [f"[{clock(s.start)}] {s.text}", ""]
    return "\n".join(lines)


def render_txt(t: Transcript, paragraph_gap: float = 1.5) -> str:
    return "\n\n".join(to_paragraphs(t.segments, paragraph_gap)) + "\n"


def render_srt(t: Transcript) -> str:
    blocks = [f"{i}\n{clock(s.start, millis=True)} --> {clock(s.end, millis=True)}\n{s.text}\n"
              for i, s in enumerate(t.segments, 1)]
    return "\n".join(blocks)


def render_vtt(t: Transcript) -> str:
    cues = [f"{clock(s.start, millis=True, dot=True)} --> {clock(s.end, millis=True, dot=True)}\n{s.text}\n"
            for s in t.segments]
    return "WEBVTT\n\n" + "\n".join(cues)


def render_tsv(t: Transcript) -> str:
    rows = ["start\tend\ttext"]
    for s in t.segments:
        rows.append(f"{s.start:.2f}\t{s.end:.2f}\t{s.text.replace(chr(9), ' ').replace(chr(10), ' ')}")
    return "\n".join(rows) + "\n"


def render_json(t: Transcript) -> str:
    return json.dumps(t.to_dict(), ensure_ascii=False, indent=2) + "\n"


_RENDERERS = {"md": render_md, "txt": render_txt, "srt": render_srt, "vtt": render_vtt, "tsv": render_tsv, "json": render_json}


def render(t: Transcript, fmt: str) -> str:
    """Render `t` in one format; `fmt` must be one of `FORMATS`."""
    return _RENDERERS[fmt](t)


def output_path(out_dir: str | os.PathLike, stem: str, fmt: str) -> pathlib.Path:
    """Where the `fmt` rendering of `stem` goes."""
    return pathlib.Path(out_dir) / (stem + _SUFFIX[fmt])


def write_outputs(
    t: Transcript,
    out_dir: str | os.PathLike,
    stem: str,
    formats: Iterable[str] = DEFAULT_FORMATS,
    overwrite: bool = True,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Write the chosen renderings; return ``(written, skipped)`` paths.

    With `overwrite=False`, a file that already exists is left alone and
    reported in `skipped`. Files are written to a temporary name and renamed,
    so a crash cannot leave a half-written transcript under a real name.
    UTF-8 without a BOM everywhere.
    """
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []
    skipped: list[pathlib.Path] = []
    for fmt in formats:
        dest = output_path(out, stem, fmt)
        if dest.exists() and not overwrite:
            skipped.append(dest)
            continue
        tmp = dest.with_name(dest.name + ".partial")
        tmp.write_text(render(t, fmt), encoding="utf-8", newline="\n")
        os.replace(tmp, dest)
        written.append(dest)
    return written, skipped


def load_transcript(path: str | os.PathLike) -> Transcript:
    """Read a ``.json`` transcript written by `write_outputs` back into a `Transcript`."""
    return Transcript.from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))


def output_stem(source: str | os.PathLike, name_template: Optional[str] = None) -> str:
    """The file stem outputs are named after: the source's stem by default.

    `name_template` may contain ``{stem}``, e.g. ``"{stem}.v2"``.
    """
    stem = pathlib.Path(source).stem
    return name_template.format(stem=stem) if name_template else stem
