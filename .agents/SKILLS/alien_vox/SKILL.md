---
name: alien_vox
description: Speak text aloud through the local speakers using AlienVox's Kokoro-82M TTS engine — local, offline, no API keys. Use when asked to speak text aloud, read something out loud, or narrate a passage; also generates a WAV file on request. Default voice is Kokoro af_heart ("American F · Heart"); other Kokoro voices are selectable. Runs on CPU by default, GPU if available.
license: MIT
compatibility: Python 3.11+, Windows/macOS/Linux; self-sufficient — requires scripts/requirements.txt installed (torch, kokoro, sounddevice, soundfile) in this skill folder's own venv.
metadata:
  author: AlienTech.Software
  version: "0.1.20260825211910"
---

# AlienVox TTS Skill

## Jobs to be Done

This skill's jobs, stated as **verb + object [+ clarifier]**:

> **Speak** text aloud *through the local speakers, offline and without an API key*
> **Normalize** text *for speech, without changing what it says*
> **Select** a voice *without changing the words*

It does not decide what to say. Enhancement is presentation only - opt-in,
deterministic, and meaning-preserving: it reflows wrapped lines, drops markup
that would otherwise be read aloud, and evens out punctuation. A rule that would
change the words belongs to the caller, not here.

Two uses. **Querying** - when a request is unclear, it is usually missing one of
the three, and asking for that part converges faster than asking someone to
explain themselves. The clarifier is where the real requirement usually hides:
*fix the tests* means something different depending on whether it ends *so they
pass* or *so they test the right thing*.

**Deciding scope** - the verb determines whether two pieces of work belong
together. Two tasks producing similar output are still two jobs if the verbs
differ. Compare verbs, not output shapes.

## Personal data boundary

This skill ships a mechanism, and stores nothing belonging to one person: no
name, contact details, home region, employment history, or account handle; no
stated preferences such as industries someone will not work in; no credentials,
and no templates or documents the user authored.

That is not a style preference. A skill carrying any of it still runs perfectly,
reports nothing, and is no longer reusable - it has become a copy of one setup,
and it leaks the moment it is shared.

Anything specific is supplied at run time by the caller or read from
user-owned configuration outside this folder, conventionally
`.personal/<this-skill>/manifest.json`, which the host keeps out of version
control. Where this skill ships an example of that configuration it lives in
`assets/` with `.example.` in the name, carries placeholders only, and is never
read at run time.

If personal configuration is required and absent, stop and say so. Never fall
back to a built-in default: a default that stands in for someone's own settings
produces output that looks valid and is not, and nothing downstream can tell.

## The learning loop

This skill owns the knowledge, the experience, the style, and the how-to for
local speech synthesis, and applies that expertise outward to whatever project it is dropped
into. It is the expert; the host is the caller.

**It is always eager to acquire and advance.** Every reference, gotcha, schema,
template, and script here exists because something was learned once and written
down so it need not be learned again.

**Whenever a calling project improves something in this domain, that is a
trigger, not a footnote.** Ask immediately:

> What can we learn and generalize from this?

Then do the work of generalizing:

1. **Name the lesson.** What actually went wrong, or what worked better than
   the previous approach.
2. **Strip the host.** Remove its vocabulary, its paths, its file layout, its
   domain language. What remains is the mechanism.
3. **Decide where it lands** — a rule in the failure-modes reference, a
   template in `assets/`, a check in a validation script, or a capability in
   the library.
4. **Prefer executable over prose.** A written rule depends on someone
   remembering it. A check does not.

**Never absorb the host's specifics while doing this.** A fix that only makes
sense for one project belongs in that project. If a lesson cannot survive
having the host's vocabulary removed, it was never a lesson about speech — it
was a lesson about that host, and it belongs there.

This is what keeps the skill portable *and* improving. Portability without
learning goes stale; learning without portability turns the skill into part of
one project.

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

## Code Blocks In The Text To Speak

If the text to speak contains code blocks (fenced ``` blocks or substantial inline code), ask the
user first whether they want the code read aloud literally or replaced with a spoken "code block"
placeholder — don't guess either way. Reading source code character-by-character/symbol-by-symbol
is rarely what's wanted and makes for a bad listening experience, but silently skipping it isn't
always right either (the user might actually want to hear it).

## Long Narration And Queued Requests

Do not send a long response as one enormous command-line argument. Instead, split it into a
**serial queue of smaller, semantically complete passages**:

- Split at section boundaries or paragraph boundaries; never split a sentence, a list item, or a
  code block in the middle.
- Prefer one to three short paragraphs per request. The goal is intelligible listening and a safe
  command-line size, not the fewest possible TTS calls.
- Play chunks in their original order and wait for each request to report success before starting
  the next. Never synthesize or play chunks concurrently: overlapping audio is unusable.
- After one chunk has finished playing, wait a short **1.5-second gap** before starting the next
  chunk. This prevents the prior audio tail or audio-device release from overlapping the next
  passage.
- Keep the default speaker-first behavior. Do not add `--out` merely because a response is long;
  create a WAV only when the user explicitly asks for one.

The current `speak.py` CLI starts a new process for each request, so separate chunks may reload
the model. This is an acceptable reliability trade-off for now. If repeated long narrations become
common, add a local batch runner that loads the engine once and consumes this same serial queue;
do not introduce a persistent MCP server solely for that optimization.

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

### Cold Starts And Resource Use

- `--device cpu` is the enforced default. It prevents GPU use, but does **not** set a memory cap:
  Torch and the Kokoro model still use normal system RAM while loading and synthesizing.
- On first use, model download and initialization can take longer than a short terminal timeout.
  `device: cpu` or model-loading warnings are not a success result. Only report playback after the
  script prints a non-zero `duration_s` and `played: true` (or an output path when a WAV was
  explicitly requested).

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

### Example: Verifying the skill itself is working (not just some other AlienVox surface)

This skill, `python_mcp_server`, and the desktop `python_app` are three separate ways to reach
AlienVox's TTS — when manually verifying by ear which one just spoke (e.g. after a change to this
skill specifically), have the spoken phrase say so explicitly, since audio alone can't otherwise
distinguish them: e.g. `python scripts/speak.py "Hello, this is the AlienVox Skill speaking."`
rather than a generic phrase. Same idea applies to `python_mcp_server` (say "MCP") if verifying
that surface instead — never the desktop app, which already announces itself correctly.

### Example: Specific voice, file only (no playback)

Request: "Generate a British male voice sample of 'The quick brown fox' and save it, don't play it."

Expected behavior:
1. Check [references/voices.md](references/voices.md) — British male is `bm_george`.
2. Run `python scripts/speak.py "The quick brown fox" --voice bm_george --out fox_sample.wav --no-play`.
3. Report the saved file path (no audible playback, since the request explicitly said not to).

### Example: Text to speak includes a code block

Request: "Read this explanation aloud" (the explanation includes a fenced ```python block).

Expected behavior: ask the user first — "Want the code block read aloud literally, or should I
just say 'code block' instead?" — before running `scripts/speak.py`, rather than guessing either
way.

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
