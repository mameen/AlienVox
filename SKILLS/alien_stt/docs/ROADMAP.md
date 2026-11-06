# Roadmap

What this skill intends but has **not** built. Nothing here is a present
capability; none of it belongs in `SKILL.md`'s description until it ships. (The
file is named `ROADMAP.md`, not `TODO.md`, so task-tracking tools do not scrape
it as a to-do list.)

Each item: **What - Why - Design - Blocked by - Effort - Status**.

## Speaker diarization (who spoke when)

- **What:** label segments with a speaker (`Speaker 1`, `Speaker 2`).
- **Why:** meetings and interviews are hard to read without it.
- **Design:** a separate diarization engine behind its own port, producing
  speaker turns that a merge step intersects with transcript segments. Not folded
  into the `SttEngine` contract: transcribing and attributing speakers are
  different jobs with different models, accuracy and licences.
- **Blocked by:** choosing a model whose licence and download terms (several
  require accepting terms or a token) are acceptable for a portable skill. That is
  a policy question before it is an engineering one.
- **Effort:** medium. **Status:** not started.

## Word-level timestamps

- **What:** `start`/`end` per word, for karaoke-style captions and precise cuts.
- **Why:** segment timing is about a second accurate.
- **Design:** `TranscribeOptions.word_timestamps` already exists and is reserved.
  Needs an engine that returns word timing reliably (cross-attention alignment or
  a forced aligner) and a `words` field in `Segment` and the JSON schema.
- **Blocked by:** a schema decision: adding `words` changes the JSON contract, so
  it needs a version marker in the file.
- **Effort:** medium. **Status:** option reserved, not implemented.

## A second engine (faster-whisper / CTranslate2)

- **What:** `--engine faster-whisper`, a lower-memory and faster runtime for the
  same Whisper weights; also a path to CPU-friendly int8.
- **Why:** speed and memory on modest hardware.
- **Design:** one new module in `alienstt/engines/` implementing `SttEngine`, one
  line in `ENGINES`. Nothing else changes; that is what the registry is for.
- **Blocked by:** nothing technical. Adds a dependency, so it must stay optional
  and degrade with a clear message when absent.
- **Effort:** small. **Status:** not started.

## Fully local Whisper setup and inference

- **What:** Make AlienSTT's Whisper path fully local after an explicit one-time
  model installation, with no runtime Hugging Face Hub requests or dependency on
  Transformers if a suitable local runtime can replace it.
- **Why:** The Type 1 voice POC needs predictable offline STT, including on a
  machine that has not already populated a Hugging Face cache. Local model
  inference should not imply that setup requires network access every time.
- **Design:** Keep model acquisition separate from transcription. Evaluate
  whisper.cpp and the existing faster-whisper/CTranslate2 option against the
  current Transformers engine for Windows, RTX 4090 performance, model quality,
  and supported Whisper model formats. Select one local runtime and provide an
  explicit model-install step; transcription must load installed files without
  contacting Hugging Face. Retain Transformers only if it remains the best
  supported runtime, and make its offline/cache requirements explicit.
- **Blocked by:** Runtime and model distribution decision; the same Whisper
  weights are not necessarily interchangeable between Transformers,
  CTranslate2, and whisper.cpp.
- **Effort:** medium. **Status:** not started.

## Subtitle re-flowing

- **What:** break long segments into cues that obey a maximum line length and
  duration, for SRT/VTT.
- **Why:** engine segments can be long for subtitles.
- **Design:** a pure function over `Segment` lists in `postprocess.py` (needs
  word timing to split precisely, hence tied to the item above).
- **Blocked by:** word-level timestamps. **Effort:** small after that.
  **Status:** not started.

## Live microphone transcription

- **What:** stream transcription from a microphone.
- **Why:** dictation.
- **Design:** a different mechanism entirely (streaming windows, voice-activity
  detection, partial results). Probably its own skill rather than an option here:
  the verb is *Dictate*, not *Transcribe*.
- **Blocked by:** a scope decision. **Status:** not started.

## Known limitations (will not change soon)

- One language per file; code-switching is not handled.
- Output is a draft; there is no accuracy score because none is trustworthy.
- Audio is decoded fully into memory before chunking (about 230 MB per hour at
  16 kHz float32). Multi-hour files work on ordinary machines; day-long ones
  would need streaming decode.
- Only Whisper-family weights are supported today.
