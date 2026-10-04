---
name: alien_stt
description: Transcribe speech from audio or video files to text with timestamps, locally and offline, using Whisper (no API key, audio never uploaded). Reads almost any format ffmpeg reads (mp3, m4a, wav, flac, ogg/opus voice notes, mp4, mkv). Also converts audio formats, probes files, splits long recordings at silences, detects the spoken language, merges and re-renders transcripts (md, txt, srt, vtt, tsv, json) and searches them by timestamp. Use when asked to transcribe, caption or subtitle a recording, turn a voice note, meeting or lecture into text, convert a voice note to mp3, or find where something was said. Not for text-to-speech.
license: MIT
compatibility: Python 3.10+, Windows/macOS/Linux; needs ffmpeg and ffprobe on PATH (or FFMPEG/FFPROBE set) and scripts/requirements.txt installed (torch, transformers, numpy, soundfile). A CUDA GPU is optional but makes large models far faster.
metadata:
  author: AlienTech.Software
  version: "0.1.20261003185931"
---

# AlienSTT Skill

This skill turns recorded speech into text. It does not decide what the speech
means, correct it, summarise it or act on it. Its output is a **draft with
timestamps and provenance** for a person to check.

## Host-project boundary

This skill is a portable mechanism that runs in a host project. The host supplies
locations, project configuration, content, dependencies, and domain decisions;
the skill supplies reusable instructions, tooling, schemas, and tests. A linked
`SKILLS/<name>` path is the same shared implementation, and work can proceed
through that visible path normally. Only the client agent composes skills; this
skill does not invoke a sibling skill.

Here that means: the host chooses which recordings to transcribe, where outputs
go and what the language is. The skill never picks a destination folder on its
own initiative, never reads a default corpus and never keeps outputs of its own
inside this folder.

## Jobs to be Done

This skill's jobs, stated as **verb + object [+ clarifier]**:

> **Transcribe** speech *from an audio or video file into timestamped text, locally and without uploading it*
> **Convert** an audio file *to another format or a slice of it, without altering the source*
> **Split** a long recording *at quiet gaps so words stay whole, and record where each piece began*
> **Detect** the spoken language *with a probability, before committing to a long run*
> **Render** a saved transcript *in another format without re-running the model*
> **Search** transcripts *for a phrase and report where it was said*

It does not interpret, correct, summarise, translate beyond Whisper's own
speech-to-English task, identify speakers, or clone or synthesise voices. It does
not decide whether a transcript is accurate enough to publish: that is a person
listening. A request that only *sounds* similar belongs elsewhere: summarising a
transcript is a writing job, and reading text aloud is the `alien_vox` job.

Two uses. **Querying**: when a request is unclear it is usually missing one of
the three parts, and asking for that part converges faster than asking someone
to explain themselves. For this skill the usual missing part is the clarifier,
*which language is spoken* and *what the transcript is for* (reading, subtitles,
search, a record someone will quote).

**Deciding scope**: the verb decides whether two pieces of work belong together.
Compare verbs, not output shapes.

## Personal data boundary

This skill ships a mechanism and stores nothing belonging to one person: no name,
contact details, home region, account handle, stated preferences, credentials, or
authored documents. It has **no personal inputs**: every value it needs (files,
language, model, output folder) arrives as an argument, and it reads no private
configuration. Its only network use is the one-time download of model weights
from Hugging Face; audio and transcripts never leave the machine.

The audio itself is personal. A recording holds someone's voice and often their
private words. Treat recordings and transcripts as the host's data: write them
only where the caller said, do not paste them into other services without being
asked, and do not put them in this folder. The run log written by `--log-dir`
deliberately contains file names and counts only, never transcript text.

If a task needs personal configuration that does not exist, stop and say so;
never fall back to a built-in default.

## Stamps

```
DATE STAMP        YYYYMMDD
DATETIME STAMP    YYYYMMDDHHmmss
```

A DATE STAMP names a day; a DATETIME STAMP names an instant to the second. Digits
only, zero padded, no separators, no zone suffix. **`MM` is month, `mm` is
minutes**; never write `hh` (12-hour clock). In Python: `%Y%m%d%H%M%S`.

**Times are Pacific**, `America/Los_Angeles`, never UTC; the zone is declared here
once and assumed everywhere. A stamp is a key: never rewrite one that was issued,
and where uniqueness matters check for a collision (Pacific repeats an hour each
autumn). The format is the whole definition; do not infer what moment it names.

This skill uses stamps in two places: the version in the frontmatter, and the
`created` field of every transcript. Run IDs are `<operation>-<DATETIME STAMP>-<4 hex>`.

## The learning loop

This skill owns the knowledge, experience, style and how-to for local speech
recognition and applies that expertise to whatever project it is dropped into. It
is the expert; the host is the caller. Every reference, gotcha and script here
exists because something was learned once and written down so it need not be
learned again.

**Whenever a calling project improves something in this domain, that is a
trigger, not a footnote.** Ask: *what can we learn and generalize from this?*

1. **Name the lesson**: what went wrong, or what worked better.
2. **Strip the host**: remove its vocabulary, paths and domain language. What is
   left is the mechanism.
3. **Decide where it lands**: a rule in `references/failure-modes.md`, an option
   in a script, a check in the library.
4. **Prefer executable over prose**: a check does not depend on anyone
   remembering it.

Never absorb the host's specifics. A fix that only makes sense for one project
belongs in that project. Worked examples already captured: text invented over
silence became the *silence guard*; stuck repetition became *repeat collapsing*;
Ogg refusing fixed bitrates at low sample rates became *quality-based Ogg
encoding*; cutting inside a breath became *wide-gap-first chunking*.

## Purpose

Produce accurate-enough, honestly labelled text from speech, on the user's own
machine. Default engine: Whisper large-v3 through Hugging Face `transformers`;
model weights are cached after the first download.

Not for: text-to-speech; live microphone dictation; speaker diarization (who said
what); word-level timestamps; any cloud speech API. See `docs/ROADMAP.md` for what
is intended but not built.

## When To Use

- "Transcribe this recording / voice note / meeting / lecture / interview"
- "Make subtitles (SRT/VTT) for this video"
- "What language is this audio in?"
- "Convert this WhatsApp voice note to mp3"
- "Split this two-hour file into 20-minute pieces"
- "Where in these recordings did they mention the budget?"

Not for: reading text aloud (that is `alien_vox`); summarising or answering
questions about a transcript (do that with the text, after transcribing).

## Required Inputs

- One or more audio/video files or folders (required).
- Spoken language (strongly recommended). Detection works on the first 30 seconds
  only and is least reliable on short clips and accented speech; naming the
  language is the single biggest accuracy lever. If unknown, run
  `detect_language.py` first, or ask.
- Output location (optional; default is next to each input).
- Formats wanted (optional; default `md,txt`).
- Names and terms likely to appear (optional); pass them with `--prompt`.

## Setup

Once per machine (the skill is self-sufficient; no sibling repo is required):

```
cd .agents/SKILLS/alien_stt
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r scripts/requirements.txt     # for a CUDA GPU install the CUDA torch build first
python scripts/check_setup.py --model large-v3
```

`check_setup.py` reports ffmpeg, ffprobe, each Python package, the GPU, and
whether the chosen model is already cached. It changes nothing and downloads
nothing. ffmpeg is a system program: install it from ffmpeg.org (or a package
manager) and make sure `ffmpeg` and `ffprobe` resolve on PATH, or set the
`FFMPEG` / `FFPROBE` environment variables to their full paths.

## Operating Procedure

1. **Check setup** if anything is unfamiliar: `python scripts/check_setup.py`.
   Stop and report if it says NOT ready; do not guess around a missing ffmpeg.
2. **Look before you run** on anything long or unknown:
   `python scripts/probe_audio.py INPUT` (duration, codec, any audio at all?).
3. **Settle the language.** Use the one the user named. If none, either ask or run
   `python scripts/detect_language.py INPUT`; below about 60% probability, ask.
4. **Transcribe**:
   ```
   python scripts/transcribe.py INPUT [INPUT ...] --lang CODE [--format md,srt,json] [--out DIR]
   ```
   Add `--dry-run` first for a big folder. Outputs that exist are skipped, so a
   re-run is cheap and safe; `--overwrite` redoes them.
5. **Verify the result**, never just the exit code:
   - the summary line says `N transcribed ... 0 failed`;
   - open the `.transcript.md` or `.txt` and read it; check the `Warning:` lines
     (low language confidence, segments dropped over silence, chunk boundaries);
   - if the text is empty, repeated, or in the wrong script, see
     `references/failure-modes.md` before re-running.
6. **Report** what was done: files, model, language (and whether it was detected),
   output paths, any warnings, and that the text is an unchecked draft.

### Choosing a model (details in references/models.md)

| Need | Use |
|---|---|
| Best accuracy, any language (default) | `--model large-v3` |
| Several times faster, slightly less accurate, esp. non-English | `--model turbo` |
| Quick draft, low memory, English | `--model small.en` or `base.en` |
| Language detection only | `--model base` |

### Tuning (all optional; defaults suit most audio)

| Symptom | Try |
|---|---|
| Names or terms misspelled | `--prompt "Name1, Name2, term"` (short, relevant) |
| Hard audio, accuracy matters more than speed | `--beam-size 5` |
| Output repeats a phrase | lower `--compression-ratio-threshold` (e.g. 1.2) |
| Real speech dropped as silence | raise `--no-speech-threshold` (e.g. 0.8) |
| Memory trouble on very long files | lower `--chunk-minutes` (e.g. 10) |
| Wrong language | name it with `--lang` |

## The tools

| Script | Job | Typical call |
|---|---|---|
| `transcribe.py` | Transcribe files/folders to md, txt, srt, vtt, tsv, json | `transcribe.py notes/ --lang en --format md,srt` |
| `convert_audio.py` | Convert or slice audio/video | `convert_audio.py note.ogg --to mp3` |
| `probe_audio.py` | Duration, codec, rate, channels, has-audio | `probe_audio.py meetings/ --json` |
| `split_audio.py` | Split at quiet gaps; writes a manifest | `split_audio.py long.mp3 --max-minutes 20 --dry-run` |
| `detect_language.py` | Language and probability | `detect_language.py clip.m4a --top 3` |
| `render_transcript.py` | Re-render saved JSON in other formats, shift times | `render_transcript.py talk.json --format srt` |
| `merge_transcripts.py` | Stitch piece transcripts onto one timeline | `merge_transcripts.py --manifest x.parts.json x.part*.json --out x.json` |
| `find_in_transcript.py` | Search transcripts with timestamps | `find_in_transcript.py "budget" transcripts/` |
| `check_setup.py` | Verify prerequisites | `check_setup.py --model turbo` |

Every script has `--help`, validates input, never overwrites without an explicit
flag, and exits non-zero on failure with a message on stderr. They are thin: all
logic is in the vendored library `alienstt/`, which Python callers can import
directly (see `README.md`).

## Long recordings

`transcribe.py` already processes files longer than `--chunk-minutes` (default 30)
in silence-aligned pieces, so memory stays bounded and no step is needed. Use
`split_audio.py` only when you want the pieces as files (to review, to parallelise,
or to meet a size limit). Then transcribe the pieces with `--format json` and join
them with `merge_transcripts.py --manifest`.

## Safety And Escalation

- Everything runs locally. The only network use is the first download of model
  weights; set `HF_HUB_OFFLINE=1` afterwards to forbid even that.
- Never modify or delete a source recording. Outputs are written beside it or in
  `--out`, atomically, and existing files are not replaced without `--overwrite`.
- Treat the transcript as a **draft**. Speech recognition mishears names, numbers,
  technical terms, mixed-language speech and unclear audio, and can write text
  that was never said. For anything quoted, published, legal, medical or
  religious, say that a person must check it against the audio. Never present
  output as verified.
- Do not claim success from an exit code alone; read the output and the warnings.
- Recordings of other people can be sensitive. Keep outputs where the user said;
  do not upload or paste them elsewhere unasked.

## Output Contract

For each input `<stem>`, in the chosen formats (default `md,txt`):

| File | Content |
|---|---|
| `<stem>.transcript.md` | provenance header, draft notice, warnings, `[mm:ss] text` lines |
| `<stem>.txt` | text only, a paragraph per pause |
| `<stem>.srt` / `<stem>.vtt` | subtitle cues |
| `<stem>.tsv` | `start`, `end`, `text` rows |
| `<stem>.json` | everything, lossless: segments plus provenance (`model`, `engine`, `device`, `language`, `language_probability`, `task`, `created`, `warnings`); the source for `render_transcript.py` |

Success: exit code 0, summary `N transcribed, M skipped, 0 failed`, the files exist
and are non-empty. Failure: non-zero exit and an `ERROR:` or `FAILED` line naming
the file and cause (no audio stream, ffmpeg missing, model not downloadable).
Formats are specified in `references/output-formats.md`.

## Examples

### Example: A voice note

Request: "Transcribe this WhatsApp voice note, it's in Arabic."

1. `python scripts/transcribe.py note.ogg --lang ar` (Ogg/Opus needs no conversion).
2. Read `note.transcript.md`; report the text as a draft and mention any warning.
3. If asked for an mp3 copy: `python scripts/convert_audio.py note.ogg --to mp3`.

### Example: Subtitles for a video

Request: "Make English subtitles for talk.mp4."

1. `python scripts/transcribe.py talk.mp4 --lang en --format srt,vtt,json`.
2. Report the `.srt`/`.vtt` paths; keep the `.json` so other formats can be made
   later with `render_transcript.py` without re-running the model.

### Example: Unknown language

Request: "What is said in clip.m4a?"

1. `python scripts/detect_language.py clip.m4a --top 3`.
2. If the top language is above about 60%, use it; otherwise ask the user.
3. Transcribe with `--lang` set. Say the language was detected and how confident.

### Example: Where was it said

Request: "Where did they mention the budget?"

1. Transcripts exist as JSON? If not, transcribe with `--format json` first.
2. `python scripts/find_in_transcript.py "budget" transcripts/ --context 1`.
3. Report file and `[mm:ss]` for each hit; offer to open the audio at those times.

### Example: Edge case, empty or repeated output

The transcript is empty, a single "Thank you", or one phrase repeated.
1. Check the `Warning:` lines: "no speech was detected" means the audio is silent
   or the language is wrong; run `probe_audio.py` and `detect_language.py`.
2. Name the language, try `--model large-v3` if turbo was used, and re-run with
   `--overwrite`. See `references/failure-modes.md`.
3. If it still fails, report that plainly; do not hand back invented text.

## Resources

- [scripts/](scripts/): the CLI tools above; [scripts/requirements.txt](scripts/requirements.txt).
- [alienstt/](alienstt/): the vendored library (audio, engines, formats, pipeline); read its module docstrings for design rationale.
- [references/models.md](references/models.md): model choices, sizes, speed and accuracy trade-offs.
- [references/output-formats.md](references/output-formats.md): every output format, field by field.
- [references/failure-modes.md](references/failure-modes.md): what goes wrong, how to recognise it, what to do.
- [docs/ROADMAP.md](docs/ROADMAP.md): intended capabilities that are not built.
- [assets/sample_speech.wav](assets/sample_speech.wav): a short real speech sample (synthetic voice) for smoke tests.
- [README.md](README.md), [AGENTS.md](AGENTS.md): human install, use and maintenance notes.
- [tests/](tests/): real tests (real ffmpeg, real model); `python -m pytest tests -v`.
