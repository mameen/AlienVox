#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stitch the transcripts of split pieces back into one transcript on one timeline.

Pairs with `split_audio.py`: split a long file, transcribe the pieces (possibly
on several machines), then merge. Each piece's times are relative to the piece;
the manifest written by `split_audio.py` says where each piece began in the
original, and this tool adds that offset.

Usage
-----
    python scripts/merge_transcripts.py --manifest lecture.parts.json PIECE.json [PIECE.json ...] --out lecture.json

    python scripts/merge_transcripts.py --manifest lecture.parts.json lecture.part*.json --out lecture.json
    python scripts/merge_transcripts.py --offsets 0,1200,2400 a.json b.json c.json --out whole.json

A piece is matched to its manifest entry by file stem (``lecture.part02.json``
matches ``lecture.part02.wav``). Without a manifest give --offsets, one number
(seconds) per input, in the same order.

The result is a normal JSON transcript (render it with `render_transcript.py`).
Provenance comes from the first piece, and a warning records that the file was
merged from pieces. Refuses to overwrite --out unless --overwrite.

Exit codes: 0 done; 1 failure; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt.cli import fail, setup_console                             # noqa: E402
from alienstt.formats import load_transcript                             # noqa: E402
from alienstt.postprocess import clean_segments, shift                   # noqa: E402


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Merge piece transcripts into one timeline.")
    p.add_argument("inputs", nargs="+", help="piece transcripts (.json), in order")
    p.add_argument("--manifest", default=None, help="the .parts.json written by split_audio.py")
    p.add_argument("--offsets", default=None, help="comma list of start offsets in seconds, one per input")
    p.add_argument("--out", required=True, help="merged transcript .json to write")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)

    files = [pathlib.Path(x) for x in args.inputs]
    if bool(args.manifest) == bool(args.offsets):
        fail("give exactly one of --manifest or --offsets", 2)
    if args.manifest:
        parts = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))["parts"]
        by_stem = {pathlib.Path(x["file"]).stem: x["start"] for x in parts}
        offsets = []
        for f in files:
            stem = f.name[:-len(".json")]
            if stem not in by_stem:
                fail(f"{f.name} has no entry in the manifest (expected a part named {stem})")
            offsets.append(by_stem[stem])
    else:
        offsets = [float(x) for x in args.offsets.split(",")]
        if len(offsets) != len(files):
            fail(f"--offsets has {len(offsets)} values for {len(files)} inputs", 2)

    out = pathlib.Path(args.out)
    if out.exists() and not args.overwrite:
        fail(f"output exists (pass --overwrite): {out}")

    pieces = sorted(zip(offsets, files), key=lambda x: x[0])
    first = load_transcript(pieces[0][1])
    segments, end = [], 0.0
    for off, f in pieces:
        t = load_transcript(f)
        segments += shift(t.segments, off)
        end = max(end, off + t.duration)
    first.segments = clean_segments(segments, max_repeat=10 ** 6)     # order and time repair only; no repeat removal across pieces
    first.duration = round(end, 2)
    first.source = first.source.split(".part")[0] or first.source
    first.warnings = list(dict.fromkeys(first.warnings + [f"merged from {len(pieces)} pieces"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(first.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(first.segments)} segments, {first.duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
