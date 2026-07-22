# Issue #005: transformers version conflict between chatterbox-tts and VibeVoice

**Status:** Resolved — `transformers==4.51.3` pinned for the whole main venv, overriding
chatterbox-tts's own declared pin. Verified for real, not just import checks.

**Reported:** 2026-07-22

## The conflict

- `chatterbox-tts` 0.1.7's wheel metadata hard-pins `transformers==5.2.0` (`Requires-Dist`, not a range).
- The `vibevoice` package (git-installed for the VibeVoice-Realtime engine) declares
  `transformers<5.0.0` (`==4.51.3` for its `streamingtts` extra specifically).

These cannot both be satisfied in one venv. A plain `pip install -r requirements.txt` with both
packages present, plus an explicit `transformers==4.51.3` pin, is a `ResolutionImpossible` for pip.

## What was tried first: two separate venvs

An earlier version of this fix ran VibeVoice out-of-process, in its own venv (`.venv-vibevoice`) with
`transformers==4.51.3`, talking to the main app over a stdin/stdout subprocess protocol. This worked, but
was reverted in favor of a single shared venv after real testing (below) showed 4.51.3 works fine for
every engine, not just VibeVoice — the extra process boundary, IPC protocol, and second venv to provision
were unneeded complexity once that was confirmed.

## Real verification that 4.51.3 works for everything

Before committing to the single-venv approach, every ML engine in this app was tested for real under
`transformers==4.51.3` — actual `from_pretrained()` calls against actual downloaded weights, actual
`generate()` calls, on a real CUDA GPU. Not import checks alone.

| Engine | Test performed | Result |
|---|---|---|
| Kokoro | Real `KPipeline` load + real synthesis | Produced real audio, no errors |
| Chatterbox-TTS | Real `ChatterboxTTS.from_pretrained()` + real `generate()` | Produced real audio (106,560 samples), no errors — despite the package declaring `transformers==5.2.0` |
| OuteTTS 0.3.3 (the version this app actually pins) | Real `InterfaceHF` load + real `generate()` | Produced real audio (112,896 samples, max amplitude 0.36), no errors |
| Piper | N/A — no transformers dependency at all | Unaffected either way |
| VibeVoice-Realtime | Real model+processor load + real `generate()` via a real voice-prompt `.pt` cache | Produced real audio (118,400 samples, max amplitude 0.67, rms 0.048) — sane, non-silent, non-exploded |

No monkeypatches were needed for any of these under 4.51.3 — the earlier subprocess/two-venv version had
accumulated three separate workarounds (an `AutoModel.register()` collision, a missing
`Qwen2TokenizerFast` module path, and a meta-device `tie_weights()` signature mismatch) purely because it
had first been tested against `transformers==5.2.0`, which `vibevoice` was never built for. None of those
issues exist under 4.51.3.

## The "newly initialized" weights warning

Loading VibeVoice under 4.51.3 logs:

```
Some weights of VibeVoiceStreamingForConditionalGenerationInference were not initialized from the model
checkpoint ... and are newly initialized: ['model.acoustic_tokenizer.encoder.downsample_layers.0.0...', ...]
You should probably TRAIN this model on a down-stream task to be able to use it for predictions and inference.
```

This is **expected and benign** for this app's usage, not a real problem: `acoustic_tokenizer.encoder`
only encodes *raw reference audio* into tokens, for cloning a voice from a raw audio clip at inference
time. AlienVox's `VibeVoiceEngine` never calls that path — every voice is a **precomputed KV-cache
"prompt"** (a `.pt` file Microsoft ships separately, see `vibevoice_engine.py`'s module docstring), not a
raw reference clip. The real-generation test above confirms the actually-used path (decoder + LM) produces
normal audio despite this warning.

There's also a tokenizer-class mismatch warning (`'Qwen2Tokenizer'` vs. `'VibeVoiceTextTokenizerFast'`) at
load time — cosmetic, doesn't affect generation; confirmed by the same real-generation test.

## The fix

`setup.py`'s `main()`:
1. Installs `requirements.txt` normally — chatterbox-tts pulls in `transformers==5.2.0` as part of this.
2. Re-asserts `numpy`/`protobuf` pins (pre-existing step, for Dia's deps).
3. **New:** re-asserts `transformers==4.51.3` (overriding chatterbox-tts's pin — verified safe above).
4. **New:** installs `vibevoice[streamingtts]` from GitHub, now compatible with the already-pinned
   `transformers==4.51.3`.

`requirements-ml.txt` documents this pin decision inline. `vibevoice_engine.py` needs zero
transformers-version workarounds under this pin — it's a plain in-process engine, same shape as every
other ML engine in this app.
