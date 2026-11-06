#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Find where something was said: search saved JSON transcripts, print timestamps.

Usage
-----
    python scripts/find_in_transcript.py PATTERN INPUT [INPUT ...] [options]

    python scripts/find_in_transcript.py "budget" meeting.json
    python scripts/find_in_transcript.py "quarterly results" transcripts/ --context 1
    python scripts/find_in_transcript.py "rev(enue|enu)" talks/ --regex --recursive
    python scripts/find_in_transcript.py "cafe" notes.json --json

Matching
--------
Plain mode folds both sides first (case, accents, and optional marks such as
Arabic vowel signs and the tatweel stretch), so ``cafe`` finds ``Café`` and an
unvoweled Arabic word finds its voweled spelling. Folding is for comparing only;
the text printed is the original. ``--regex`` matches a Python regular expression
against the original text, case-insensitively, with no folding.

Output: ``file [mm:ss] text`` per hit, with ``--context N`` neighbouring segments
around it. ``--json`` prints a list of hits with exact start/end seconds.
Read-only.

Exit codes: 0 at least one hit; 1 none (like grep) or error; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt.cli import fail, setup_console                             # noqa: E402
from alienstt.formats import clock, load_transcript                      # noqa: E402
from alienstt.postprocess import normalize_for_search                    # noqa: E402


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Search JSON transcripts and print timestamps.")
    p.add_argument("pattern", help="text to find (or a regex with --regex)")
    p.add_argument("inputs", nargs="+", help="transcript .json files or folders")
    p.add_argument("--regex", action="store_true", help="treat PATTERN as a regular expression")
    p.add_argument("--context", type=int, default=0, metavar="N", help="also show N segments before and after each hit")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--json", action="store_true", help="print hits as JSON")
    args = p.parse_args(argv)

    if args.regex:
        try:
            rx = re.compile(args.pattern, re.IGNORECASE)
        except re.error as exc:
            fail(f"bad regular expression: {exc}", 2)
        matches = lambda text: bool(rx.search(text))                      # noqa: E731
    else:
        needle = normalize_for_search(args.pattern)
        if not needle:
            fail("the pattern is empty after normalisation", 2)
        matches = lambda text: needle in normalize_for_search(text)       # noqa: E731

    files: list[pathlib.Path] = []
    for item in args.inputs:
        q = pathlib.Path(item)
        if q.is_dir():
            files += sorted(q.rglob("*.json") if args.recursive else q.glob("*.json"))
        elif q.is_file():
            files.append(q)

    hits = []
    for f in files:
        try:
            t = load_transcript(f)
        except (ValueError, KeyError, OSError):
            continue                                                       # a .json that is not a transcript
        segs = t.segments
        for i, s in enumerate(segs):
            if matches(s.text):
                lo, hi = max(0, i - args.context), min(len(segs), i + args.context + 1)
                hits.append({"file": f.name, "start": s.start, "end": s.end, "text": s.text,
                             "context": [{"start": c.start, "text": c.text} for c in segs[lo:hi]]})

    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        for h in hits:
            if args.context:
                for c in h["context"]:
                    mark = ">" if c["start"] == h["start"] and c["text"] == h["text"] else " "
                    print(f"{h['file']} {mark}[{clock(c['start'])}] {c['text']}")
                print()
            else:
                print(f"{h['file']} [{clock(h['start'])}] {h['text']}")
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
