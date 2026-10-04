#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-render saved JSON transcripts as other formats, without touching a model.

The `.json` written by `transcribe.py --format json` is the lossless copy of a
transcript. This tool turns it into Markdown, plain text, SRT, WebVTT or TSV on
demand, so a decision like "also give me subtitles" or "paragraphs break at 3 s
instead" costs a second, not another transcription run.

Usage
-----
    python scripts/render_transcript.py TRANSCRIPT.json [...] --format srt,vtt [--out DIR] [options]

    python scripts/render_transcript.py talk.json --format srt
    python scripts/render_transcript.py transcripts/ --format all --out rendered/
    python scripts/render_transcript.py talk.json --format txt --paragraph-gap 3
    python scripts/render_transcript.py talk.json --format srt --offset 90      # shift cues 90 s later

--offset shifts every time by that many seconds (use it when a recording was
trimmed or joined after transcription). Existing outputs are skipped unless
--overwrite. Folders are scanned for ``*.json`` files that look like transcripts.

Exit codes: 0 done; 1 failure or nothing found; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt.base import Transcript                                     # noqa: E402
from alienstt.cli import fail, setup_console                             # noqa: E402
from alienstt.formats import load_transcript, parse_formats, write_outputs  # noqa: E402
from alienstt.postprocess import shift                                   # noqa: E402


def find_transcripts(inputs, recursive: bool) -> list[pathlib.Path]:
    """Expand files/folders to ``*.json`` files that contain a ``segments`` list."""
    found: list[pathlib.Path] = []
    for item in inputs:
        p = pathlib.Path(item)
        cands = ([p] if p.is_file() else sorted(p.rglob("*.json") if recursive else p.glob("*.json")) if p.is_dir() else [])
        for c in cands:
            try:
                if isinstance(json.loads(c.read_text(encoding="utf-8")).get("segments"), list):
                    found.append(c)
            except (ValueError, OSError, AttributeError):
                continue
    return found


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Re-render JSON transcripts in other formats.")
    p.add_argument("inputs", nargs="+", help="transcript .json files or folders of them")
    p.add_argument("--format", default="md,txt,srt", help="comma list of md,txt,srt,vtt,tsv,json or 'all' (default %(default)s)")
    p.add_argument("--out", default=None, metavar="DIR", help="output folder (default: next to each input)")
    p.add_argument("--paragraph-gap", type=float, default=1.5, help="seconds of silence that start a paragraph in .txt")
    p.add_argument("--offset", type=float, default=0.0, metavar="SEC", help="shift all times by this many seconds")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--overwrite", action="store_true", help="replace existing outputs (default: skip)")
    args = p.parse_args(argv)

    try:
        formats = parse_formats(args.format)
    except ValueError as exc:
        fail(str(exc), 2)
    files = find_transcripts(args.inputs, args.recursive)
    if not files:
        fail("no transcript .json files found in the given inputs")

    rc = 0
    for f in files:
        try:
            t: Transcript = load_transcript(f)
            if args.offset:
                t.segments = shift(t.segments, args.offset)
            stem = f.name[:-len(".json")]
            # Never write the same JSON back over its own source.
            fmts = [x for x in formats if not (x == "json" and not args.out)]
            written, skipped = write_outputs(t, args.out or f.parent, stem, fmts, overwrite=args.overwrite)
            for w in written:
                print(f"wrote {w}")
            for s in skipped:
                print(f"kept existing {s}")
        except Exception as exc:
            rc = 1
            print(f"FAILED {f.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
