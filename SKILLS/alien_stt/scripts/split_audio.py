#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Split a long recording into pieces, cutting in quiet gaps so words stay whole.

Why split: a multi-hour file is easier to review, transcribe in parallel on
several machines, or hand to a tool with a size limit when it is in pieces. The
transcription pipeline already chunks internally for memory; this tool is for
when you want the pieces as files.

Usage
-----
    python scripts/split_audio.py INPUT [--max-minutes 20 | --segment-seconds 90] [options]

    python scripts/split_audio.py lecture.mp3 --max-minutes 20 --out parts/
    python scripts/split_audio.py call.wav --max-minutes 10 --dry-run          # show the plan only
    python scripts/split_audio.py noisy.m4a --max-minutes 15 --threshold-db -32 --min-silence 0.6

Modes
-----
* default (silence-aware): each cut lands in the middle of the latest quiet gap
  that fits under the limit. If a stretch has no gap, that piece is hard-cut at
  the limit and the tool says so, because a hard cut can split a word.
* --fixed: equal-length cuts at exactly --max-minutes / --segment-seconds.

Outputs
-------
`<stem>.part01.<ext>`, `<stem>.part02.<ext>` ... and `<stem>.parts.json`, a
manifest recording each piece's start offset in the original. Feed that
manifest to `merge_transcripts.py` to stitch the pieces' transcripts back into
one timeline.

Existing parts are never overwritten unless --overwrite. Nothing is written with
--dry-run. The source file is never modified.

Exit codes: 0 done; 1 failure; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt import audio as audio_mod                                  # noqa: E402
from alienstt.cli import fail, human_duration, setup_console             # noqa: E402


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Split a recording into pieces at quiet gaps.")
    p.add_argument("input", help="audio or video file")
    size = p.add_mutually_exclusive_group()
    size.add_argument("--max-minutes", type=float, default=None, help="longest piece, in minutes (default 20)")
    size.add_argument("--segment-seconds", type=float, default=None, help="longest piece, in seconds")
    p.add_argument("--fixed", action="store_true", help="cut at exact lengths instead of in quiet gaps")
    p.add_argument("--min-seconds", type=float, default=30.0, help="shortest allowed piece when seeking a quiet gap (default 30)")
    p.add_argument("--threshold-db", type=float, default=-40.0, help="below this level (dBFS) counts as quiet; raise toward -30 for noisy audio")
    p.add_argument("--min-silence", type=float, default=0.4, help="shortest quiet gap that may hold a cut, seconds")
    p.add_argument("--format", default="wav", metavar="EXT", help="piece format (default wav; use mp3/flac to save space)")
    p.add_argument("--out", default=None, metavar="DIR", help="output folder (default: next to the input)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")
    p.add_argument("--overwrite", action="store_true", help="replace existing parts")
    args = p.parse_args(argv)

    src = pathlib.Path(args.input)
    if not src.is_file():
        fail(f"not a file: {src}")
    limit = args.segment_seconds if args.segment_seconds else (args.max_minutes or 20.0) * 60.0
    if limit <= 0:
        fail("the piece length must be positive", 2)

    try:
        samples = audio_mod.decode(src)
        duration = samples.size / audio_mod.SAMPLE_RATE
        quiet = [] if args.fixed else audio_mod.quiet_ranges(samples, threshold_db=args.threshold_db, min_silence=args.min_silence)
        pieces = audio_mod.plan_chunks(duration, quiet, limit, min_seconds=min(args.min_seconds, limit))
    except audio_mod.AudioError as exc:
        fail(str(exc))

    mids = [(a + b) / 2 for a, b in quiet]
    print(f"{src.name}: {human_duration(duration)} -> {len(pieces)} piece(s), {len(quiet)} quiet gap(s) found")
    hard = 0
    for i, (a, b) in enumerate(pieces, 1):
        in_gap = i == len(pieces) or any(abs(b - m) < 1e-6 for m in mids) or args.fixed
        hard += 0 if in_gap else 1
        print(f"  part {i:02d}: {a:8.1f}s - {b:8.1f}s ({human_duration(b - a)})" + ("" if in_gap else "  hard cut (no quiet gap)"))
    if hard:
        print(f"warning: {hard} hard cut(s) may split a word; raise --threshold-db or --max-minutes to find gaps", file=sys.stderr)
    if args.dry_run:
        return 0

    out_dir = pathlib.Path(args.out or src.parent)
    ext = "." + args.format.lower().lstrip(".")
    manifest = {"source": src.name, "duration": round(duration, 2), "parts": []}
    try:
        for i, (a, b) in enumerate(pieces, 1):
            dst = out_dir / f"{src.stem}.part{i:02d}{ext}"
            audio_mod.convert(src, dst, start=a, duration=b - a, overwrite=args.overwrite)
            manifest["parts"].append({"file": dst.name, "start": round(a, 3), "end": round(b, 3)})
            print(f"  wrote {dst}")
    except audio_mod.AudioError as exc:
        fail(str(exc))
    mpath = out_dir / f"{src.stem}.parts.json"
    if mpath.exists() and not args.overwrite:
        fail(f"manifest exists (pass --overwrite): {mpath}")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
