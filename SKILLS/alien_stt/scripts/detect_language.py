#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Identify the spoken language of audio files, with probabilities.

Run this before a big batch when the language is not certain: a wrong
language setting is the most common cause of useless transcripts, and detection
costs seconds while transcription costs minutes.

Usage
-----
    python scripts/detect_language.py INPUT [INPUT ...] [--top 3] [--model turbo] [--device auto] [--json]

    python scripts/detect_language.py note.ogg
    python scripts/detect_language.py interviews/ --top 3 --json

Only the first 30 seconds are examined. Short clips, heavy accents, code-switching
and background music make the result less reliable; read the probability, not just
the name. A probability under about 60% means "name the language yourself".

Read-only. Exit codes: 0 done; 1 a file failed or none found.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt import audio as audio_mod                                  # noqa: E402
from alienstt.cli import fail, setup_console                             # noqa: E402
from alienstt.engines import DEFAULT_ENGINE, DEFAULT_MODEL, ENGINES, get_engine  # noqa: E402


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Detect the spoken language of audio files.")
    p.add_argument("inputs", nargs="+", help="files or folders")
    p.add_argument("--top", type=int, default=3, help="how many candidate languages to show (default 3)")
    p.add_argument("--engine", default=DEFAULT_ENGINE, choices=sorted(ENGINES))
    p.add_argument("--model", default=DEFAULT_MODEL, help="a smaller model (e.g. base) is plenty for detection and loads faster")
    p.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda", "gpu"))
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--json", action="store_true", help="print a JSON list")
    args = p.parse_args(argv)

    files, notes = audio_mod.collect_inputs(args.inputs, recursive=args.recursive)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    if not files:
        fail("no audio or video files found in the given inputs")

    engine = get_engine(args.engine, model=args.model, device=args.device)
    rows, failed = [], 0
    for f in files:
        try:
            head = audio_mod.decode(f, duration=30.0)
            scores = engine.language_scores(head, top=args.top)
            rows.append({"file": f.name, "languages": [{"code": c, "probability": round(pr, 3)} for c, pr in scores]})
        except Exception as exc:
            failed += 1
            rows.append({"file": f.name, "error": f"{type(exc).__name__}: {exc}"})
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            if "error" in r:
                print(f"{r['file']}: ERROR {r['error']}")
            else:
                print(f"{r['file']}: " + ", ".join(f"{x['code']} {x['probability']:.0%}" for x in r["languages"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
