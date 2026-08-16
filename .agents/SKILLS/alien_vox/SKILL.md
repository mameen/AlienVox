---
name: alien_vox
description: Speak text aloud through the local speakers using AlienVox's Kokoro-82M TTS engine — local, offline, no API keys. Use when asked to speak text aloud, read something out loud, or narrate a passage; also generates a WAV file on request. Default voice is Kokoro af_heart ("American F · Heart"); other Kokoro voices are selectable. Runs on CPU by default, GPU if available.
license: MIT
compatibility: Python 3.11+, Windows/macOS/Linux; self-sufficient — requires scripts/requirements.txt installed (torch, kokoro, sounddevice, soundfile) in this skill folder's own venv.
metadata:
  author: AlienTech.Software
  version: "0.1.20260816000000"
---

# AlienVox TTS Skill

## Purpose

Turn text into real, locally-synthesized speech, played immediately through the local default
audio output device, using AlienVox's Kokoro-82M engine — no network calls at inference time (only
the one-time ~300MB model download from Hugging Face Hub on first use), no API keys. A `.wav` file
is only written when explicitly requested (`--out`) — playing it is the default outcome, not
producing a file nobody opens.

Not for: editing/transcribing existing audio, speech-to-text, or any TTS engine other than Kokoro
(the only one this skill's vendored [`alienvox_tts`](alienvox_tts/) library ships today — see
`references/voices.md` for why, and how to add another engine later).

## When To Use

- "Read this text aloud" / "speak this" / "say this out loud"
- "Generate a voice sample of ___"
- "Create a text-to-speech audio file for ___"
- "Narrate this passage"

Not for: requests naming a different TTS engine/provider (ElevenLabs, Azure, OpenAI TTS, etc.) —
this skill only wraps AlienVox's local Kokoro engine. Not for speech-to-text/transcription requests.

## Required Inputs

- The text to speak (required).
- Voice (optional — defaults to `af_heart`, "American F · Heart"). See
  [references/voices.md](references/voices.md) for the full roster of 7 voices.
- Device (optional — defaults to `cpu`, the real enforced default; pass `--device gpu` to opt into
  CUDA if a real GPU is present, falls back to CPU automatically if not).
- Whether a `.wav` file is also wanted (optional — off by default; playback alone is the default
  outcome).

## Operating Procedure

1. Confirm this skill's own dependencies are installed (a one-time step; this skill is
   self-sufficient — no sibling repo dependency):
   ```
   cd .agents/SKILLS/alien_vox
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r scripts/requirements.txt
   ```
2. Run [`scripts/speak.py`](scripts/speak.py):
   ```
   python scripts/speak.py "Text to speak here" [--voice af_heart] [--device cpu|gpu] [--no-play] [--out output.wav]
   ```
3. By default the script plays the audio through the local default output device and prints
   `sample_rate`/`duration_s`/`played: true`. Pass `--out` to also write a real `.wav` file (its
   path is then printed too); pass `--no-play` to suppress playback (requires `--out` — running
   with both suppressed does real synthesis work and discards it, which the script refuses).
4. Verify the result: check the printed duration is non-zero — a zero duration or a nonzero exit
   code means synthesis failed; report the script's stderr, don't claim success.

## Safety And Escalation

- Purely local, offline synthesis (after the one-time model download) — no data leaves the
  machine, no confirmation checkpoint needed for the synthesis itself.
- Playback uses the local audio output device and **will make audible sound on the user's
  machine by default** — that's the intended, expected outcome for a "speak this" request; only
  pass `--no-play` when the user specifically wants a silent file instead.
- Never fabricate an audio file's existence or contents — always actually run the script and check
  its real output before reporting success.

## Output Contract

- Real audio played through the local output device (default), and/or a real `.wav` file at the
  requested path if `--out` was given (24kHz mono float32→int16 PCM).
- Script exit code 0 and a printed `duration_s`/`sample_rate`/`played` on success; non-zero exit
  code and an error message on failure (empty text, unknown voice after fallback, missing
  dependencies, `--no-play` without `--out`, etc.).

## Examples

### Example: Basic speech generation

Request: "Say 'Welcome to AlienVox' out loud."

Expected behavior:
1. Run `python scripts/speak.py "Welcome to AlienVox"` (no flags needed — plays by default).
2. Confirm the script printed a real duration, `played: true`, and exit code 0.

### Example: Specific voice, file only (no playback)

Request: "Generate a British male voice sample of 'The quick brown fox' and save it, don't play it."

Expected behavior:
1. Check [references/voices.md](references/voices.md) — British male is `bm_george`.
2. Run `python scripts/speak.py "The quick brown fox" --voice bm_george --out fox_sample.wav --no-play`.
3. Report the saved file path (no audible playback, since the request explicitly said not to).

### Example: Unknown/invalid voice

Request: "Speak this using the 'robot' voice."

Expected behavior: the vendored `alienvox_tts`'s `KokoroEngine` falls back to `af_heart` for any unrecognized
voice id rather than erroring — the script will succeed but with the default voice, not silently
claim "robot" was used. Report this fallback explicitly to the user rather than staying quiet
about it, since it's not what they asked for.

## Resources

- [scripts/speak.py](scripts/speak.py) — the CLI wrapper (imports the vendored `alienvox_tts/` directly).
- [alienvox_tts/](alienvox_tts/) — the vendored TTS library itself (self-sufficient copy).
- [references/voices.md](references/voices.md) — full Kokoro voice roster and how to add engines.
- [assets/sample_af_heart.wav](assets/sample_af_heart.wav) — a real, pre-generated sample of the
  default voice, for reference/comparison (not required to run anything).
- [AGENTS.md](AGENTS.md) — standalone-copy checklist for this skill folder.
- [tests/test_kokoro.py](tests/test_kokoro.py) — real synthesis tests for the vendored library.
