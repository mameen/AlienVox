# Issue #006: VibeVoice occasional generation quality artifacts (cut-short audio, hallucinated background music)

**Status:** Open — captured, not fixable in this app's code (see "Why this isn't a code bug"
below). Tracking so it isn't lost/re-investigated from scratch later.
**Reported:** 2026-07-22
**Scope:** `src/engines/vibevoice_engine.py`, `src/audio_player.py` — investigated, not the root
cause; the underlying VibeVoice model itself.

---

## Reports

Two real-preview reports in the same session, different voices, same `vibevoice_realtime` model,
CPU device:

1. **Emma**: playback "cut short less than a second before the end."
2. **Grace**: the generated audio had audible background music mixed into the speech.

## Investigation

**Cut-short audio:** `audio_player.py`'s `play_audio()` already calls `sd.wait()` (blocks until all
samples are handed to the OS mixer) followed by a settle delay specifically added for a prior,
similar "audio cut off near the end" bug (commit: "Fix audible playback tail-cut bug shared by
every ML engine"). `vibevoice_engine.py`'s `_do_speak()` only marks the engine `_done` *after*
`play_audio()` returns, so `wait_until_done()` callers can't be racing ahead of real playback
completion. The settle delay was bumped 0.3s → 0.6s as a cheap, safe hedge, but this is **not
confirmed** to be the actual root cause — it's equally plausible VibeVoice's own `generate()` ended
the audio abruptly (autoregressive generation stopping on an EOS-like condition slightly early),
which no amount of playback-side settle delay would fix.

**Background music:** Traced the full pipeline — `_synthesize_array()` takes VibeVoice's raw
`generate()`/`speech_outputs[0]` tensor, applies volume scaling (`apply_volume()`, pure
multiplication), and hands the result straight to `play_audio()`. There is no mixing, EQ,
resampling-with-artifacts, or any other audio-injection code anywhere in this pipeline that could
add music. The music has to be present in the raw model output itself.

## Why this isn't a code bug

Both symptoms are consistent with a known limitation already documented in this codebase:
`vibevoice_engine.py`'s `apply_volume()` docstring notes VibeVoice's "real autoregressive
generation isn't reproducible enough call-to-call" — confirmed by real testing (two identical
real generations produced different token counts, and once a *higher* peak at supposedly lower
volume). Hallucinated background sound/music and inconsistent output length are both well-known
failure modes of autoregressive TTS models generally, and nothing in this app's code path could
introduce them — the audio played is exactly the model's raw output.

## What would actually help (not attempted — out of scope for a code fix)

- Re-running the same voice/text and comparing — if it's non-deterministic (which
  `apply_volume()`'s docstring already established for token count), a second attempt on the same
  input may not reproduce either symptom.
- Trying `do_sample=False` vs sampling settings, or a different `cfg_scale`, in
  `vibevoice_engine.py`'s `generate()` call — a model-tuning question, not a bug fix; would need
  deliberate A/B testing across many voices/phrases before changing the shipped defaults, since
  the current settings (`do_sample=False`, `cfg_scale=1.0`) were carried over from the upstream
  demo script, not independently tuned.
- Reporting upstream to Microsoft's VibeVoice repo if this reproduces consistently for a specific
  voice.
