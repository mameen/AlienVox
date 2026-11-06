#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Transcribe audio or video files to text, locally, with timestamps.

Thin CLI over the vendored `alienstt` library (../alienstt): argument parsing,
progress and reporting only. Every real decision (decoding, chunking,
decoding quality checks, formats) lives in the library, so this file and a
Python caller behave identically.

Usage
-----
    python scripts/transcribe.py INPUT [INPUT ...] [options]

    python scripts/transcribe.py recording.mp3 --lang en
    python scripts/transcribe.py notes/ --lang ar --format md,srt,json --out transcripts/
    python scripts/transcribe.py talk.mp4 --task translate --model turbo
    python scripts/transcribe.py a.m4a --prompt "Kubernetes, Istio, Dr. Rahman" --beam-size 5

INPUT is a file or a folder. A folder contributes the media files directly
inside it (add --recursive to descend). Any format ffmpeg reads works.

Behaviour worth knowing
-----------------------
* Outputs go next to each input, or into --out. An output that already exists
  is **skipped**, not overwritten, so re-running a folder only does new files.
  Pass --overwrite to redo.
* If every requested output for a file already exists the file is not even
  decoded.
* The model loads once and is reused for the whole batch.
* One bad file does not stop the batch (use --fail-fast to stop). The exit code
  is non-zero if any file failed.
* --dry-run lists what would be done and loads nothing.
* --log-dir writes a JSONL event log (no transcript text in it) for auditing.

Exit codes: 0 all files done or skipped; 1 at least one file failed or no input
found; 2 bad arguments.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt import audio as audio_mod                                    # noqa: E402
from alienstt.base import TranscribeOptions                                # noqa: E402
from alienstt.cli import fail, human_duration, setup_console               # noqa: E402
from alienstt.engines import DEFAULT_ENGINE, DEFAULT_MODEL, ENGINES, get_engine  # noqa: E402
from alienstt.formats import DEFAULT_FORMATS, output_path, output_stem, parse_formats, write_outputs  # noqa: E402
from alienstt.pipeline import transcribe_file                              # noqa: E402
from alienstt.trace import RunLog                                          # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Transcribe audio/video to text locally (Whisper by default).")
    p.add_argument("inputs", nargs="+", help="audio/video files or folders")

    g = p.add_argument_group("what to transcribe")
    g.add_argument("--lang", default=None, metavar="CODE", help="spoken language, e.g. en, ar, fr. Omit to detect (less reliable than naming it)")
    g.add_argument("--task", choices=("transcribe", "translate"), default="transcribe", help="translate = write English text from any language")
    g.add_argument("--prompt", default=None, help="text that biases spelling of names and terms; short and relevant works best")
    g.add_argument("--prompt-file", default=None, metavar="FILE", help="read the prompt from a UTF-8 file")
    g.add_argument("--recursive", action="store_true", help="descend into sub-folders of folder inputs")

    g = p.add_argument_group("engine and model")
    g.add_argument("--engine", default=DEFAULT_ENGINE, choices=sorted(ENGINES), help=f"speech engine (default {DEFAULT_ENGINE})")
    g.add_argument("--model", default=DEFAULT_MODEL, help=f"alias (large-v3, turbo, medium, small, base, tiny) or Hugging Face id/path (default {DEFAULT_MODEL})")
    g.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda", "gpu"), help="auto uses a GPU when one is really available")

    g = p.add_argument_group("decoding quality (defaults suit most audio)")
    g.add_argument("--beam-size", type=int, default=1, help="1 = greedy and fastest; 5 is slower and a little more accurate")
    g.add_argument("--temperature", default="0.0,0.2,0.4,0.6,0.8,1.0", help="comma list; the fallback ladder used when a window fails the checks")
    g.add_argument("--no-speech-threshold", type=float, default=0.6, help="above this (and low confidence) a window is treated as silence")
    g.add_argument("--compression-ratio-threshold", type=float, default=1.35, help="lower = stricter against repetition loops")
    g.add_argument("--logprob-threshold", type=float, default=-1.0, help="windows less confident than this are re-decoded")
    g.add_argument("--chunk-minutes", type=float, default=30.0, help="process files longer than this in silence-aligned pieces; 0 disables")

    g = p.add_argument_group("output")
    g.add_argument("--out", default=None, metavar="DIR", help="output folder (default: next to each input)")
    g.add_argument("--format", default=",".join(DEFAULT_FORMATS), help="comma list of md,txt,srt,vtt,tsv,json or 'all' (default %(default)s)")
    g.add_argument("--name-template", default=None, metavar="T", help="output name, may use {stem}, e.g. '{stem}.v2'")
    g.add_argument("--paragraph-gap", type=float, default=1.5, help="seconds of silence that start a new paragraph in .txt")
    g.add_argument("--overwrite", action="store_true", help="replace outputs that already exist (default: skip them)")

    g = p.add_argument_group("run control")
    g.add_argument("--dry-run", action="store_true", help="list what would be done; load no model")
    g.add_argument("--fail-fast", action="store_true", help="stop at the first failing file")
    g.add_argument("--log-dir", default=None, metavar="DIR", help="write a JSONL event log here (no transcript text is logged)")
    g.add_argument("--quiet", action="store_true", help="only errors and the final summary")
    g.add_argument("--json-summary", action="store_true", help="print the run summary as one JSON line at the end")
    return p


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)

    try:
        formats = parse_formats(args.format)
        temps = tuple(float(x) for x in args.temperature.split(",") if x.strip())
    except ValueError as exc:
        fail(str(exc), 2)
    if args.prompt_file:
        args.prompt = pathlib.Path(args.prompt_file).read_text(encoding="utf-8").strip()

    options = TranscribeOptions(
        language=args.lang, task=args.task, beam_size=args.beam_size, temperature=temps,
        compression_ratio_threshold=args.compression_ratio_threshold, logprob_threshold=args.logprob_threshold,
        no_speech_threshold=args.no_speech_threshold, prompt=args.prompt, chunk_seconds=args.chunk_minutes * 60.0,
    )

    log = RunLog("transcribe", args.log_dir, quiet=args.quiet)
    files, notes = audio_mod.collect_inputs(args.inputs, recursive=args.recursive)
    for n in notes:
        log.say(f"note: {n}")
    log.event("run_started", engine=args.engine, model=args.model, device=args.device, language=args.lang,
              task=args.task, formats=formats, overwrite=args.overwrite, argv=sys.argv[1:])
    log.event("input_resolved", files=len(files), notes=len(notes))
    if not files:
        fail("no audio or video files found in the given inputs")

    def targets(f: pathlib.Path):
        out_dir = pathlib.Path(args.out) if args.out else f.parent
        return out_dir, output_stem(f, args.name_template)

    todo = []
    for f in files:
        out_dir, stem = targets(f)
        existing = [output_path(out_dir, stem, fmt) for fmt in formats if output_path(out_dir, stem, fmt).exists()]
        if existing and len(existing) == len(formats) and not args.overwrite:
            log.event("item_skipped", item=f.name, reason="outputs exist")
            log.say(f"skip {f.name} (outputs exist; --overwrite to redo)")
            continue
        todo.append(f)

    if args.dry_run:
        for f in todo:
            log.say(f"would transcribe {f}")
        log.say(f"dry run: {len(todo)} to do, {len(files) - len(todo)} skipped")
        return 0

    engine = None
    failed = 0
    for i, f in enumerate(todo, 1):
        log.event("item_started", item=f.name, index=i, total=len(todo))
        try:
            if engine is None:
                log.say(f"loading {args.model} ...")
                engine = get_engine(args.engine, model=args.model, device=args.device)
            log.say(f"[{i}/{len(todo)}] {f.name}")
            t = transcribe_file(f, engine, options)
            out_dir, stem = targets(f)
            written, skipped = write_outputs(t, out_dir, stem, formats, overwrite=args.overwrite)
            for w in written:
                log.output(w)
                log.say(f"  wrote {w}")
            for s in skipped:
                log.say(f"  kept existing {s}")
            for w in t.warnings:
                log.say(f"  warning: {w}")
            log.event("item_complete", item=f.name, duration_s=t.duration, language=t.language,
                      segments=len(t.segments), warnings=len(t.warnings), model=t.model, device=t.device)
        except KeyboardInterrupt:
            log.event("run_finished", level="WARN", status="interrupted")
            raise
        except Exception as exc:                          # one bad file must not hide the rest of the batch
            failed += 1
            log.event("item_failed", level="ERROR", item=f.name, error_type=type(exc).__name__, error=str(exc))
            log.say(f"  FAILED {f.name}: {type(exc).__name__}: {exc}", error=True)
            if args.fail_fast:
                break

    summary = log.summary()
    log.event("run_finished", status="failed" if failed else "ok", **{k: summary[k] for k in ("complete", "skipped", "failed")})
    skipped_total = summary["skipped"]
    log.say(f"done: {summary['complete']} transcribed, {skipped_total} skipped, {summary['failed']} failed "
            f"in {human_duration(summary['elapsed_s'])}" + (f"; log {summary['log']}" if summary["log"] else ""))
    if args.json_summary:
        print(json.dumps(summary, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
