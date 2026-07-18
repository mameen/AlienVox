# State-of-the-Art Free and Local Text-to-Speech Models

**Updated:** 2026-07-18  
**Project constraint:** AlienVox must use TTS engines that are free to use or can run locally. Paid cloud APIs must not be required for core functionality.

This document tracks practical, verified TTS options for AlienVox. The project is local-first: cloud APIs can be useful for experiments, but they are not acceptable as the default or only speech path.

## Decision Summary

| Rank | Model / Engine | Role | Free / Local Fit | Status |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Kokoro-82M | Primary local neural TTS target | Open weights, local, Apache 2.0 | Recommended |
| 2 | Native OS TTS | Fast baseline and fallback | Built into Windows/macOS/Linux | Recommended |
| 3 | Piper | Small offline fallback | Local, MIT, archived upstream | Recommended fallback |
| 4 | VibeVoice-Realtime-0.5B | Streaming local TTS experiment | Open source, MIT, local-capable | Experimental |
| 5 | Zonos v0.1 / ZONOS2 | High-quality local experiment | Open weights, Apache 2.0, heavier GPU path | Experimental |
| 6 | Dia | Dialogue / expressive research path | Open weights, Apache 2.0, GPU-oriented | Experimental |
| No | Gemini TTS / ElevenLabs / OpenAI TTS | Cloud-only premium engines | Not local; paid/rate-limited risk | Optional demo only |

## Recommended Local Engines

### 1. Kokoro-82M

- **Upstream:** https://huggingface.co/hexgrad/Kokoro-82M
- **License:** Apache 2.0.
- **Model size:** 82M parameters.
- **Why it fits AlienVox:** Small enough for desktop use, local, permissive, and realistic as a first neural voice target.
- **Implementation note:** Prefer integrating through an existing maintained local runtime first, then evaluate a native Rust/ONNX/Candle path only after the product loop works.
- **Risk:** Quality and language support depend on available voices and runtime wrappers. Do not promise full multilingual coverage without testing the chosen voice pack.

### 2. Native OS TTS

- **Windows:** WinRT `Windows.Media.SpeechSynthesis` first; SAPI 5 as fallback.
- **macOS:** `AVSpeechSynthesizer`.
- **Linux:** Speech Dispatcher.
- **Why it fits AlienVox:** Free, offline, lowest integration risk, very low startup latency.
- **Role:** Always keep this path available, even if a neural model is added. It is the reliability floor.

### 3. Piper

- **Upstream:** https://github.com/rhasspy/piper
- **License:** MIT.
- **Status:** Original `rhasspy/piper` repository is archived/read-only as of 2025-10-06.
- **Why it fits AlienVox:** Fast, small, local neural TTS with many downloadable voice models.
- **Correction from previous docs:** Do not use invented voice tier names such as "Vellum Tiny." Piper voices are commonly distributed by quality tiers such as `x_low`, `low`, `medium`, and `high`.
- **Risk:** Upstream archival means maintenance risk. Treat as a stable fallback, not the main innovation path.

## Experimental Local Engines

### VibeVoice-Realtime-0.5B

- **Upstream:** https://github.com/microsoft/VibeVoice
- **License:** MIT.
- **Model size:** 0.5B parameters.
- **Capabilities:** Real-time streaming TTS, streaming text input, and long-form speech generation.
- **Why it fits AlienVox:** It is open source, local-capable, and aligned with a free/local requirement.
- **Why it is not the default:** Microsoft marks VibeVoice as research/development-oriented and does not recommend commercial or real-world application use without further testing and development. It also needs direct measurement on the target Windows machine before being promoted.
- **Role:** Candidate local neural engine to benchmark against Kokoro-82M.

### Zonos v0.1 and ZONOS2

- **Upstreams:** https://github.com/Zyphra/Zonos and https://huggingface.co/Zyphra/ZONOS2
- **License:** Apache 2.0.
- **Capabilities:** High-fidelity speech, voice cloning, style/emotion control, multilingual support.
- **Why it is not the default:** Zonos-class models are heavier than Kokoro and have GPU/runtime complexity. ZONOS2 is Linux/NVIDIA-oriented in its current local inference path.
- **Role:** Good for a high-quality local experiment after the MVP capture/playback loop is working.

### Dia

- **Upstreams:** https://github.com/nari-labs/dia and https://huggingface.co/nari-labs/Dia-1.6B
- **License:** Apache 2.0.
- **Capabilities:** Expressive dialogue generation, speaker tags, nonverbal cues, audio conditioning.
- **Current limitation:** English-focused and GPU-oriented; the full model has significant VRAM requirements.
- **Role:** Useful for dialogue/storytelling experiments, not the first desktop read-selection engine.

## Cloud Models

### Gemini TTS

- **Upstreams:** https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-preview-tts and https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
- **Fit for AlienVox core:** No.
- **Reason:** Gemini TTS is cloud/API-based. It may offer free-tier access, but it is still subject to billing, quotas, preview/stability changes, and network availability.
- **Allowed use:** Optional proof-of-concept adapter only, disabled by default, never required for the app to function.

## Removed Entries

The following entries were removed because they were unverified, inaccurate, out of scope, or not suitable for a free/local-first decision document:

- VibeVoice-Realtime-0.5B sub-80ms TTFA claim: the model is verified, but that specific benchmark claim was not verified. The upstream repo describes roughly 300 ms first audible latency.
- Fish Audio S2 / S2 Pro claims: previous size and WER figures were not verified.
- Pocket TTS: no authoritative upstream source was cited.
- dots.tts: no authoritative upstream source was cited.
- Wan Streamer v0.1 / `arXiv:2606.25041`: appears fabricated or irrelevant to a TTS utility.

## Required Validation Before Implementation

Before committing to any neural model implementation:

1. Generate the same sample text through each candidate.
2. Measure cold start, time to first audio, and real-time factor on the target Windows machine.
3. Measure memory and disk footprint.
4. Verify license for both inference code and model weights.
5. Confirm the model can run without paid services or mandatory network calls after installation.
