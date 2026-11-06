# alien_stt: AlienSTT speech-to-text skill

Turns audio and video into timestamped text on your own machine. Whisper
large-v3 by default, no API key, nothing uploaded. Reads almost any format
ffmpeg reads: mp3, m4a, wav, flac, ogg/opus voice notes, mp4, mkv, and more.

It is the speech-to-text sibling of [`alien_vox`](../alien_vox/) (text-to-speech),
built the same way: self-sufficient folder, vendored library, thin scripts, real
tests, a `SKILL.md` an agent can follow. See [`SKILL.md`](SKILL.md) for the
agent-facing definition, [`AGENTS.md`](AGENTS.md) for maintenance rules.

## Install

```bat
cd .agents/SKILLS/alien_stt
python -m venv .venv
.venv\Scripts\activate
pip install -r scripts/requirements.txt
python scripts/check_setup.py
```

For a CUDA GPU install the CUDA build of torch first (see the note in
`scripts/requirements.txt`). Install ffmpeg separately (ffmpeg.org or a package
manager) so `ffmpeg` and `ffprobe` are on `PATH`; or point the `FFMPEG` and
`FFPROBE` environment variables at them. `check_setup.py` tells you what is
missing and changes nothing.

## Use

```bat
python scripts/transcribe.py recording.mp3 --lang en
python scripts/transcribe.py notes/ --lang ar --format md,srt,json --out transcripts/
python scripts/transcribe.py talk.mp4 --task translate --model turbo
```

| Tool | What it does |
|---|---|
| `transcribe.py` | Transcribe files or folders; md, txt, srt, vtt, tsv, json; skips finished work; JSONL run log |
| `convert_audio.py` | Convert or slice audio/video (voice note to mp3, video to wav, a time range) |
| `probe_audio.py` | Duration, codec, sample rate, channels, size, has-audio |
| `split_audio.py` | Split a long file at quiet gaps; writes a manifest of offsets |
| `detect_language.py` | Spoken language with probabilities |
| `render_transcript.py` | Re-render saved JSON in other formats; shift times |
| `merge_transcripts.py` | Join piece transcripts onto one timeline |
| `find_in_transcript.py` | Search transcripts, print `[mm:ss]` hits |
| `check_setup.py` | Verify prerequisites |

Every tool has `--help`. Common options on `transcribe.py`: `--lang`, `--model`
(`large-v3`, `turbo`, `medium`, `small`, `base`, `tiny`, any Hugging Face id),
`--task transcribe|translate`, `--device auto|cpu|cuda`, `--beam-size`,
`--prompt`, `--chunk-minutes`, `--format`, `--out`, `--overwrite`, `--dry-run`,
`--log-dir`. Details: [`references/models.md`](references/models.md),
[`references/output-formats.md`](references/output-formats.md).

## Use as a library

```python
from alienstt import get_engine, transcribe_file, TranscribeOptions, write_outputs

engine = get_engine("whisper", model="turbo")          # loads lazily, reuse for many files
t = transcribe_file("meeting.mp3", engine, TranscribeOptions(language="en", prompt="Kubernetes"))
print(t.text)
write_outputs(t, "out", "meeting", formats=["md", "srt", "json"])
```

Layers, bottom to top: `base` (data model and engine contract), `device`,
`audio` (ffmpeg), `postprocess`, `formats`, `trace`, `engines/` (registry),
`pipeline`. Importing the package does not import torch; the audio, formats and
trace layers work with only ffmpeg and numpy installed. Add an engine by writing
one class in `alienstt/engines/` and registering it.

## What to expect

- A **draft**. Names, numbers, technical terms, mixed-language speech and unclear
  audio get mis-heard, and models can invent text over silence. The silence guard
  and repeat collapsing remove the commonest of those; a person still has to
  check anything that matters. Every Markdown output says so in its header.
- Naming the language (`--lang`) beats detection. Detection reads only the first
  30 seconds.
- Long files are processed in silence-aligned chunks automatically.
- Re-running a folder only does the files that have no outputs yet.

[`references/failure-modes.md`](references/failure-modes.md) lists what goes
wrong and what to do. [`docs/ROADMAP.md`](docs/ROADMAP.md) lists what is intended
but not built (speaker labels, word timestamps, a second engine).

## Test

```bat
python -m pytest tests -v
```

Real tests, no mocking of internals: real ffmpeg, a real speech recording
(`assets/sample_speech.wav`), and the real Whisper model. Tests that need
something missing (ffmpeg, torch, the model in the Hugging Face cache) **skip**
with the reason; they never download weights. The suite uses
`openai/whisper-large-v3-turbo`, so cache it first if you want the model tests to run.

## Package

```bat
python build.py
```

Writes `.build/alien_stt.zip` (without `.venv`, caches and tests' temp files), a
self-contained copy to unzip on another machine.
