# TODO #011: Support lightweight local TTS engines

**Status:** Implemented; performance review remains open  
**Created:** 2026-11-04  
**Scope:** Pocket TTS, Supertonic 3, MOSS-TTS-Nano, and existing Kokoro support

## Decision

### Hard deployment constraint

All supported engines must be free to run locally and must work without a paid API,
API key, subscription, or hosted inference endpoint. Model downloads may come from a
public repository such as Hugging Face, but inference must happen on the user's machine
and continue to work offline after the model and required voice assets are installed.

Any candidate whose normal path requires a paid service, mandatory cloud inference, or
credentials is rejected. Optional first-run downloads must be explicit, resumable, and
installable through the existing model-management flow.

Keep Qwen3-TTS 0.6B in the catalog as an optional engine because it is already
implemented and tested, but do not make it the default or present it as the preferred
lightweight model. The developer's listening assessment is that its quality is poor.

Kokoro-82M is already supported and remains the default lightweight baseline.

Add support for:

1. **Pocket TTS** — first priority; ~100M, CPU-focused, streaming, voice cloning.
2. **Supertonic 3** — evaluate as a small multilingual ONNX/CPU engine.
3. **MOSS-TTS-Nano** — evaluate as a small multilingual CPU/ONNX engine.

## Acceptance bar

Each new engine must have:

- a real `TtsEngine` adapter, not a placeholder;
- a catalog entry with explicit weight size, license, languages, and install method;
- lazy imports so the base application still starts without the engine installed;
- a model-specific weight directory and uninstall path;
- voice enumeration and deterministic invalid-voice behavior;
- CPU synthesis on Windows where the upstream supports it;
- a real audio smoke test gated only by absent optional dependencies/weights;
- a performance entry using the canonical AlienVox sample phrase;
- at least one listening sample committed under the normal installer-assets rules;
- dependency and license verification before shipping.

## Research gates

Before implementation is considered complete, verify from upstream sources:

- exact package/API and Windows support;
- model and code licenses, including cloned/custom voice restrictions;
- whether ONNX is an official supported path or a community conversion;
- CPU memory use, first-audio latency, real-time factor, and maximum text length;
- whether the model supports streaming and voice cloning in the intended adapter.

## Implementation order

1. Confirm Kokoro regression baseline and isolate optional dependency groups.
2. Implement Pocket TTS adapter and run CPU quality/performance comparison.
3. Implement Supertonic 3 adapter only after its official runtime/API is verified.
4. Implement MOSS-TTS-Nano adapter only after its ONNX package and license are verified.
5. Add catalog/installer/health/UI entries and real tests for each accepted engine.
6. Compare all four lightweight engines using the same phrase, voices, CPU/GPU mode,
   first-audio latency, real-time factor, memory, and subjective listening notes.

## Current model positioning

| Model | Status | Position |
|---|---|---|
| Kokoro-82M | Supported | Default lightweight engine |
| Qwen3-TTS 0.6B | Supported and real-tested | Optional; developer dislikes quality |
| Pocket TTS | Implemented and real-tested | CPU; uses public preset voice states; current shared NumPy 1 runtime requires `--no-deps` installation |
| Supertonic 3 | Implemented and real-tested | CPU ONNX; 31-language upstream model |
| MOSS-TTS-Nano | Implemented and real-tested | Official ONNX runtime; CPU synthesis is slow and memory-heavy |

## Implementation and local CPU measurements

All samples below use the canonical phrase defined by `SAMPLE_TEXT` in
`src/control/app_controller.py`. The app performance harness results are from this
Windows CPU, with local weights and no hosted inference. RSS includes the Python process.

| Engine / voice | Synthesis | Audio | RTF | Process RSS | Sample |
|---|---:|---:|---:|---:|---|
| Pocket TTS / Alba | 8.40 s | 7.20 s | 1.17 | 1,181 MB | `install/assets/audio/ml/pockettts/alba.mp3` |
| Supertonic 3 / M1 | 2.12 s | 8.99 s | 0.24 | 501 MB | `install/assets/audio/ml/supertonic3/M1.mp3` |
| MOSS-TTS-Nano / Ava | 31.46 s | 30.00 s | 1.05 | 9,722 MB | `install/assets/audio/ml/moss_tts_nano/Ava.mp3` |
| Qwen3-TTS 0.6B / Vivian | 32.25 s | 10.56 s | 3.05 | 2,913 MB | `install/assets/audio/ml/qwen3tts/vivian.mp3` |

The first MOSS benchmark runs appeared to return only two samples. This was a bug in
the performance harness: it counted the channel dimension instead of frames for
`(frames, channels)` audio. The harness now reports frame count, duration, and total
PCM bytes correctly; the rerun agrees with the 30-second real synthesis sample.
MOSS reached the runtime's 30-second frame cap and remains memory-heavy; listening
review is still needed. Measurements are single runs, not benchmark claims.

Targeted model/config/registry tests: 152 passed. A combined real-model coverage run
passed 40 tests. The full Windows suite then reported 436 passed, 12 skipped, 33 failed,
and 57% total coverage in the isolated environment. Eleven Manage Voices failures were
stale controller/UI test assumptions; after updating that test fixture and assertions,
all 11 Manage Voices tests pass. Other full-suite failures include unavailable optional
engine packages, a clipboard-state failure, and native SAPI COM exceptions.

Latest engine-module coverage from the full run: Pocket 81%, Supertonic 93%, MOSS 88%,
and Qwen 94%. Under Transformers 4.57.3, VibeVoice tests passed 20/1 skipped and
Chatterbox tests passed 13/2 skipped, including real local synthesis. The global 80%
gate was not met in the isolated full-suite environment (57%); several optional engine
packages were absent, and Windows SAPI COM and clipboard tests failed independently.
