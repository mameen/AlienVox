#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convert or slice audio/video files to another audio format with ffmpeg.

Typical jobs: a WhatsApp Ogg/Opus voice note to MP3 for sharing, a video to its
audio track, a stereo recording to 16 kHz mono WAV, the first two minutes of a
long file.

Usage
-----
    python scripts/convert_audio.py INPUT [INPUT ...] [--to mp3] [--out DIR] [options]

    python scripts/convert_audio.py note.ogg                       # note.mp3 next to it
    python scripts/convert_audio.py clips/ --to wav --sample-rate 16000 --channels 1
    python scripts/convert_audio.py talk.mp4 --to mp3 --bitrate 96k --out audio/
    python scripts/convert_audio.py long.mp3 --to flac --start 60 --duration 120

Safe by default: an existing destination is **never** overwritten unless you
pass --overwrite, the source is never modified, and the output is written under a
temporary name and renamed on success so a crash leaves no half-file.
Metadata (tags, embedded art) is dropped from the output.

Exit codes: 0 all converted; 1 at least one file failed or none found; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt import audio as audio_mod                    # noqa: E402
from alienstt.cli import fail, setup_console               # noqa: E402


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Convert or slice audio/video files with ffmpeg.")
    p.add_argument("inputs", nargs="+", help="files or folders")
    p.add_argument("--to", default="mp3", metavar="EXT", help="output format by extension: mp3, wav, flac, ogg, opus, m4a ... (default mp3)")
    p.add_argument("--out", default=None, metavar="DIR", help="output folder (default: next to each input)")
    p.add_argument("--sample-rate", type=int, default=None, metavar="HZ", help="resample, e.g. 16000")
    p.add_argument("--channels", type=int, default=None, choices=(1, 2), help="1 = mono, 2 = stereo")
    p.add_argument("--bitrate", default=None, metavar="RATE", help="lossy formats only, e.g. 128k (sensible default per format)")
    p.add_argument("--start", type=float, default=None, metavar="SEC", help="start this many seconds in")
    p.add_argument("--duration", type=float, default=None, metavar="SEC", help="keep only this many seconds")
    p.add_argument("--recursive", action="store_true", help="descend into sub-folders")
    p.add_argument("--overwrite", action="store_true", help="replace existing outputs (default: refuse)")
    args = p.parse_args(argv)

    ext = "." + args.to.lower().lstrip(".")
    files, notes = audio_mod.collect_inputs(args.inputs, recursive=args.recursive, dedupe=False)
    for n in notes:
        print(f"note: {n}")
    # Never treat an output we would produce as an input in the same folder scan.
    files = [f for f in files if f.suffix.lower() != ext or args.out]
    if not files:
        fail("no audio or video files found in the given inputs")

    failed = 0
    for f in files:
        dst = pathlib.Path(args.out or f.parent) / (f.stem + ext)
        try:
            audio_mod.convert(f, dst, sample_rate=args.sample_rate, channels=args.channels, bitrate=args.bitrate,
                              start=args.start, duration=args.duration, overwrite=args.overwrite)
            print(f"{f.name} -> {dst}")
        except audio_mod.AudioError as exc:
            failed += 1
            print(f"FAILED {f.name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
