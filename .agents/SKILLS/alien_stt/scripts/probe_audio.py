#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Report duration, codec, sample rate, channels and size of audio/video files.

Use it before a long transcription to estimate the work and to catch files that
have no audio stream at all, and afterwards to confirm a conversion did what
was asked.

Usage
-----
    python scripts/probe_audio.py INPUT [INPUT ...] [--json] [--recursive]

    python scripts/probe_audio.py recording.m4a
    python scripts/probe_audio.py meetings/ --recursive --json > inventory.json

Read-only: nothing is decoded, converted or written.

Exit codes: 0 every file probed; 1 at least one file unreadable or without audio, or none found.
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
    p = argparse.ArgumentParser(description="Probe audio/video files with ffprobe.")
    p.add_argument("inputs", nargs="+", help="files or folders")
    p.add_argument("--json", action="store_true", help="machine-readable output: a JSON list, one object per file")
    p.add_argument("--recursive", action="store_true", help="descend into sub-folders")
    args = p.parse_args(argv)

    files, notes = audio_mod.collect_inputs(args.inputs, recursive=args.recursive, dedupe=False)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    if not files:
        fail("no audio or video files found in the given inputs")

    rows, failed = [], 0
    for f in files:
        try:
            rows.append(audio_mod.probe(f).to_dict())
        except audio_mod.AudioError as exc:
            failed += 1
            rows.append({"path": str(f), "error": str(exc)})
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            if "error" in r:
                print(f"{pathlib.Path(r['path']).name}: ERROR {r['error']}")
                continue
            print(f"{pathlib.Path(r['path']).name}: {human_duration(r['duration'])} ({r['duration']:.1f}s), "
                  f"{r['audio_codec']}, {r['sample_rate']} Hz, {r['channels']} ch, "
                  f"{r['size_bytes'] / 1024:.0f} KiB" + (", has video" if r["has_video"] else ""))
        total = sum(r.get("duration", 0) for r in rows)
        if len(rows) > 1:
            print(f"total: {len(rows)} files, {human_duration(total)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
