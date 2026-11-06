# Output formats

Chosen with `--format a,b,c` (or `all`). Files are UTF-8 without a BOM, written
atomically (temporary name, then renamed). An existing output is skipped unless
`--overwrite` is given.

| Format | File | For |
|---|---|---|
| `md` | `<stem>.transcript.md` | People: provenance header and `[mm:ss]` lines |
| `txt` | `<stem>.txt` | Plain text, a paragraph per pause (`--paragraph-gap`, default 1.5 s) |
| `srt` | `<stem>.srt` | Subtitle editors and most video players |
| `vtt` | `<stem>.vtt` | Browsers (`<track>`), web video |
| `tsv` | `<stem>.tsv` | Spreadsheets and scripts |
| `json` | `<stem>.json` | Everything; the lossless source for the others |

The `.transcript.md` double suffix keeps the Markdown from colliding with a
hand-written `<stem>.md`. `--name-template '{stem}.v2'` renames all outputs.

## Markdown

```
# Transcript: talk.mp3

- Source: `talk.mp3`
- Model: `openai/whisper-large-v3` (whisper, cuda)
- Language: en (99% confidence)
- Length: 12:40
- Made: 2026-10-03 by alienstt
- Note: An automatic draft, not checked by a person. ...
- Warning: ...            (zero or more)

[00:00] First segment text

[00:07] Second segment text
```

`Language` shows a confidence only when the language was *detected*; if you named
it with `--lang` there is none. For `--task translate` it adds ", translated to English".

## SRT and WebVTT

SRT cues are numbered and use `HH:MM:SS,mmm --> HH:MM:SS,mmm`. WebVTT starts with
`WEBVTT`, has no numbers, and uses `.` before the milliseconds. One cue per
recognised segment; the engine's own segmentation is not re-flowed to a
characters-per-line rule, so cues can be long. Re-flowing is on the roadmap.

## TSV

Header row `start<TAB>end<TAB>text`, times in seconds with two decimals. Tabs and
newlines inside text are replaced by spaces.

## JSON

```json
{
  "source": "talk.mp3",
  "segments": [{"start": 0.0, "end": 6.8, "text": "..."}],
  "duration": 760.2,
  "language": "en",
  "language_probability": 0.991,
  "model": "openai/whisper-large-v3",
  "engine": "whisper",
  "device": "cuda",
  "task": "transcribe",
  "created": "20261003190555",
  "warnings": [],
  "text": "all segment text joined"
}
```

- Times are **seconds from the start of the source file**, even when the file was
  processed in chunks or merged from pieces.
- `language_probability` is `null` when the language was supplied (not measured)
  or the model is English-only.
- `created` is a DATETIME STAMP (`YYYYMMDDHHmmss`, Pacific time).
- Unknown keys are ignored on load, so newer files open in older versions.
- `text` is derived from `segments`; if you edit one, regenerate the other.

## Run log (optional)

`--log-dir DIR` writes `<run_id>.jsonl`: one event per line with `ts` (UTC, ISO
8601), `level`, `event`, `run_id` and fields. Events: `run_started`,
`input_resolved`, `item_started`, `item_complete`, `item_skipped`, `item_failed`,
`run_finished`. It carries file names, counts, durations and settings, **never
transcript text**. `--json-summary` prints the final counts and output paths as
one JSON line on stdout.
