# AlienVox Technology Options: Free and Local TTS

**Updated:** 2026-07-18  
**Project constraint:** Core TTS must be free to use or run locally. Paid cloud APIs must not be required.

This document defines the implementation options for AlienVox. The product goal is a lightweight cross-platform "read selected text" utility with a dependable local speech path.

## Architecture Decision

AlienVox should use a provider-based TTS interface:

```text
Selection Capture
  -> Text Normalization
  -> TTS Provider
       1. Native OS TTS fallback
       2. Local neural TTS, starting with Kokoro-82M
       3. Optional local experimental engines, including VibeVoice-Realtime
       4. Optional cloud demo adapters, disabled by default
  -> Audio Playback / Stop Control
```

The application must work without an API key, billing account, or active internet connection after local dependencies are installed.

## Option 1: Native OS TTS

### Windows

- **Primary API:** `Windows.Media.SpeechSynthesis`.
- **Fallback API:** SAPI 5 `ISpVoice`.
- **Why it fits:** Built in, free, offline, fast, and suitable for the MVP latency target.
- **Tradeoff:** Voice quality depends on installed Windows voices and may sound less natural than neural models.

### macOS

- **Primary API:** `AVSpeechSynthesizer`.
- **Personal Voice:** Possible future enhancement on supported macOS versions after explicit user authorization.
- **Why it fits:** Built in, free, offline, and aligned with the native "speak selection" behavior AlienVox is trying to match.

### Linux

- **Primary API:** Speech Dispatcher.
- **Why it fits:** Standard Linux speech interface and compatible with accessibility tooling.
- **Tradeoff:** Voice quality and setup vary by distribution.

## Option 2: Rust `tts` Crate

- **Upstream:** https://crates.io/crates/tts
- **Role:** Thin cross-platform wrapper over native OS speech systems.
- **Why it fits:** Good first integration layer for the MVP because it reduces platform-specific code.
- **Use when:** The crate exposes enough control for rate, pitch, volume, voice selection, stop, and interruption.
- **Do not assume:** That it solves neural model inference. It is a native-backend bridge, not a local neural TTS runtime.

## Option 3: Kokoro-82M Local Neural TTS

- **Upstream:** https://huggingface.co/hexgrad/Kokoro-82M
- **License:** Apache 2.0.
- **Model size:** 82M parameters.
- **Role:** First high-quality local neural target.
- **Why it fits:** Good quality-to-size ratio, local execution, permissive license, realistic desktop footprint.
- **Implementation route:** Start with the most reliable existing local runtime. Only move toward ONNX/Candle/Rust-native inference after measuring quality and latency.
- **Requirement:** Must be runnable without paid API calls.

## Option 4: Piper Offline TTS

- **Upstream:** https://github.com/rhasspy/piper
- **License:** MIT.
- **Status:** Original upstream is archived/read-only.
- **Role:** Small offline neural fallback.
- **Why it fits:** Proven local TTS engine with small voice models.
- **Correction:** Do not refer to "Vellum Tiny"; use real Piper voice quality tiers such as `x_low`, `low`, `medium`, and `high`.
- **Risk:** Maintenance has moved away from the original repository, so avoid depending on future upstream development.

## Option 5: Heavier Local Neural Engines

### VibeVoice-Realtime-0.5B

- **Upstream:** https://github.com/microsoft/VibeVoice
- **License:** MIT.
- **Role:** Streaming local neural TTS candidate.
- **Strengths:** 0.5B parameter size, streaming text input, real-time TTS focus, local-capable open-source path.
- **Constraint:** Microsoft describes VibeVoice as research/development-oriented and recommends further testing before commercial or real-world application use. Benchmark locally before treating it as production-ready.
- **Implementation route:** Test through the upstream Python/Hugging Face path first. Add a native wrapper only after latency, quality, and memory measurements pass.

### Zonos v0.1 / ZONOS2

- **Upstreams:** https://github.com/Zyphra/Zonos and https://huggingface.co/Zyphra/ZONOS2
- **License:** Apache 2.0.
- **Role:** High-quality local experiment.
- **Strengths:** Voice cloning, expressive control, multilingual support.
- **Constraint:** Heavier runtime and GPU-oriented local inference make it unsuitable as the first MVP engine.

### Dia

- **Upstreams:** https://github.com/nari-labs/dia and https://huggingface.co/nari-labs/Dia-1.6B
- **License:** Apache 2.0.
- **Role:** Dialogue/storytelling experiment.
- **Strengths:** Speaker-tagged dialogue, emotional/nonverbal cues, audio conditioning.
- **Constraint:** English-focused and GPU-oriented; not ideal for fast read-selection playback.

## Option 6: Cloud TTS Adapters

Cloud TTS adapters are allowed only as optional demos or user-enabled extensions. They must not be part of the default product path.

### Gemini TTS

- **Upstreams:** https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-preview-tts and https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
- **Reason not default:** Cloud/API dependency, quotas, preview changes, and billing risk.
- **Allowed role:** Optional adapter behind explicit configuration.

### Other Paid Cloud Providers

- Examples: ElevenLabs, OpenAI TTS, Azure Neural Voice.
- **Reason not default:** They require network access and/or paid usage.
- **Allowed role:** Optional adapter only.

## Removed / Corrected Claims

The previous version included claims that must not guide implementation:

- `Qwen3-TTS-rs`: repository, model figures, and latency claims were not verified.
- `any-tts`: crate and adapter claims were not verified.
- `Voxtral` as TTS: incorrect; Voxtral is speech-understanding/ASR-oriented, not a TTS engine.
- Piper "Vellum Tiny": not real Piper terminology.
- VibeVoice-Realtime-0.5B sub-80ms TTFA: model is verified, but that specific benchmark was not verified. Use upstream's roughly 300 ms first audible latency claim until local measurements exist.
- Cloud AI voices as a high-priority product path: conflicts with the free/local requirement.

## Recommended Implementation Order

1. Implement the provider interface and native OS TTS path.
2. Add playback interruption and reliable stop behavior.
3. Add Kokoro-82M as the first local neural engine.
4. Benchmark VibeVoice-Realtime-0.5B against Kokoro-82M for streaming latency and voice quality.
5. Add Piper only if Kokoro is too heavy or unreliable on target machines.
6. Evaluate Zonos or Dia after the core app is stable.
7. Keep cloud adapters out of the critical path.

## Acceptance Criteria

- App can speak selected text without internet.
- App can speak selected text without API keys.
- App can stop current speech immediately.
- App preserves the native OS fallback even when neural models are unavailable.
- Any model shipped or downloaded by the app has verified license terms for both code and weights.
