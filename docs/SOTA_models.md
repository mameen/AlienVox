# State-of-the-Art Free and Local Text-to-Speech Models

**Updated:** 2026-07-27  
**Project constraint:** AlienVox must use TTS engines that are free to use or can run locally. Paid cloud
APIs must not be required for core functionality.

This document tracks the full model landscape for AlienVox — what is implemented, what is ready for
evaluation, and what has been ruled out. The project is local-first: cloud APIs can be useful for
experiments, but they are not acceptable as the default or only speech path.

For per-option architecture details and the ADR queue, see
[`docs/tts_technology_options.md`](tts_technology_options.md).

---

## Decision Summary

| Rank | Model / Engine | Role | Free / Local Fit | Status |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Kokoro-82M | Primary local neural TTS | Open weights, Apache 2.0, local | **Implemented** |
| 2 | Native OS TTS | Fast baseline and fallback | Built into Windows/macOS/Linux | **Implemented** |
| 3 | Chatterbox 0.5B | High-quality local TTS | Open weights, Apache 2.0, local | **Implemented** |
| 4 | F5-TTS | High-quality local TTS | Open weights, MIT, local | **Implemented** |
| 5 | Dia 1.6B | Expressive dialogue TTS | Open weights, Apache 2.0, GPU-oriented | **Implemented** |
| 6 | OuteTTS 0.5B | Good-quality local TTS | Open weights, local | **Implemented** |
| 7 | Piper | Small offline neural fallback | Local, MIT, archived upstream | Stub (TBD) |
| 8 | VibeVoice-Realtime-0.5B | Streaming local TTS experiment | Open source, MIT, local-capable | Experimental |
| 9 | Zonos v0.1 / ZONOS2 | High-quality local experiment | Open weights, Apache 2.0, GPU-oriented | Experimental |
| — | Gemini TTS / ElevenLabs / OpenAI TTS | Cloud-only premium engines | Not local; paid/rate-limited risk | Optional demo only |

---

## Implemented Engines

### Kokoro-82M

- **Upstream:** https://huggingface.co/hexgrad/Kokoro-82M
- **License:** Apache 2.0.
- **Model size:** 82M parameters.
- **Why it fits AlienVox:** Small enough for desktop use, local, permissive, and realistic as a first
  neural voice target.
- **Risk:** Quality and language support depend on available voices and runtime wrappers.

### Native OS TTS

- **Windows:** WinRT `Windows.Media.SpeechSynthesis` first; SAPI 5 as fallback.
- **macOS:** `AVSpeechSynthesizer`.
- **Linux:** Speech Dispatcher.
- **Why it fits AlienVox:** Free, offline, lowest integration risk, very low startup latency.
- **Role:** Always keep this path available, even if a neural model is added. It is the reliability floor.

### Chatterbox 0.5B

- **Upstream:** https://github.com/resemble-ai/chatterbox
- **License:** Apache 2.0.
- **Model size:** ~500M parameters.
- **Capabilities:** High naturalness, voice cloning, streaming-capable.
- **Why it fits:** On-device, permissive license, good balance of quality and footprint.

### F5-TTS

- **Upstream:** https://github.com/SWivid/F5-TTS
- **License:** MIT.
- **Model size:** ~335M parameters.
- **Capabilities:** Flow-matching TTS, voice cloning from short reference.
- **Why it fits:** Permissive license, on-device, competitive quality.

### Dia 1.6B

- **Upstreams:** https://github.com/nari-labs/dia and https://huggingface.co/nari-labs/Dia-1.6B
- **License:** Apache 2.0.
- **Capabilities:** Expressive dialogue generation, speaker tags, nonverbal cues, audio conditioning.
- **Current limitation:** English-focused and GPU-oriented; the full model has significant VRAM
  requirements.
- **Role:** Useful for dialogue/storytelling experiments, not the first desktop read-selection engine.

### OuteTTS 0.5B

- **Upstream:** https://huggingface.co/OuteAI/OuteTTS-0.3-500M
- **License:** Check upstream — verify before shipping.
- **Model size:** 500M parameters.
- **Capabilities:** On-device, reasonable quality for standard read-selection use.

### Piper

- **Upstream:** https://github.com/rhasspy/piper
- **License:** MIT.
- **Status:** Original `rhasspy/piper` repository is archived/read-only as of 2025-10-06.
- **Implementation status:** Stub only (`piper_win.py` returns `b""`). Requires ONNX runtime,
  per-voice `.onnx` + `.onnx.json` files, and `piper-phonemize`. See `todo_002.md`.
- **Correction:** Do not use invented voice tier names such as "Vellum Tiny." Use real quality tiers:
  `x_low`, `low`, `medium`, `high`.
- **Risk:** Upstream archival means maintenance risk. Treat as a stable fallback, not the main
  innovation path.

---

## Experimental Engines

### VibeVoice-Realtime-0.5B

- **Upstream:** https://github.com/microsoft/VibeVoice
- **License:** MIT.
- **Model size:** 0.5B parameters.
- **Capabilities:** Real-time streaming TTS, streaming text input, and long-form speech generation.
- **Why it fits AlienVox:** Open source, local-capable, aligned with the free/local requirement.
- **Why it is not the default:** Microsoft marks VibeVoice as research/development-oriented and does not
  recommend commercial or real-world use without further testing. Requires direct measurement on the
  target Windows machine before being promoted.
- **Note:** Previously claimed sub-80ms TTFA — not verified. Upstream describes roughly 300 ms first
  audible latency.

### Zonos v0.1 and ZONOS2

- **Upstreams:** https://github.com/Zyphra/Zonos and https://huggingface.co/Zyphra/ZONOS2
- **License:** Apache 2.0.
- **Capabilities:** High-fidelity speech, voice cloning, style/emotion control, multilingual support.
- **Why it is not the default:** Heavier than Kokoro; ZONOS2 is Linux/NVIDIA-oriented in its current
  local inference path.
- **Role:** Good for a high-quality local experiment after the MVP capture/playback loop is working.

---

## Candidates Under Evaluation (todo_008)

These models are surfaced from the Voicebox roadmap and have not yet been formally evaluated against
AlienVox's requirements. Full research questions and evaluation criteria are in
`python_app/docs/issues/todo_008_model_landscape_evaluation.md`.

### Evaluation rubric

**Green** — can move toward implementation:
- Permissive or clearly acceptable license (code **and** weights)
- Real CPU path or another first-class non-CUDA path
- Installable in a way that can be reproduced in a frozen build
- No hidden preset-voice asset trap
- API is understandable without a large wrapper layer

**Yellow** — interesting, but needs one of these before it can ship:
- Platform gating
- Manual install instructions
- Special asset provisioning
- A non-trivial packaging workaround
- A policy decision about commercial use

**Red** — keep out of the shipping catalog for now:
- CPU path missing or broken upstream
- Windows packaging clearly unstable
- Install requires too much bespoke patching
- API would distort AlienVox's architecture
- Licensing or usage terms too uncertain

### TTS candidates

| Candidate | Notes |
|-----------|-------|
| Pocket TTS | No authoritative upstream source cited yet — needs verification |
| IndicF5 | Indian-language F5-TTS variant; evaluate license and Windows CPU path |
| VibeVoice | Already in Experimental above; deeper CPU/Windows evaluation needed |
| FireRedTTS-2 | Evaluate license, CPU path, Windows packaging |
| LongCat-AudioDiT | Evaluate license, CPU path, install story |
| SoproTTS | Evaluate license, CPU path |
| NeuTTS Air / Nano | Evaluate license, model size, CPU viability |
| dots.tts | No authoritative upstream source cited yet — needs verification |
| Maya1 | Evaluate license, model size, CPU path |
| X-Voice | Evaluate license, upstream repo, CPU path |

### STT candidates

| Candidate | Notes |
|-----------|-------|
| Nemotron 3.5 ASR Streaming 0.6B | Evaluate streaming capability, Windows CPU, license |
| Cohere Transcribe 03-2026 | Verify if on-device or cloud-only; cloud path = excluded by default |
| ARK-ASR 3B / 0.6B | Evaluate license, CPU path, Windows packaging |
| IBM Granite Speech 4.1 2B / NAR | Evaluate license, CPU path, install story |

### Watch / blocked

| Candidate | Reason |
|-----------|--------|
| VoxCPM / VoxCPM2 | CPU/MPS support not ready upstream; revisit when platform support improves |

---

## Cloud Models

### Gemini TTS

- **Upstreams:** https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-preview-tts and
  https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
- **Fit for AlienVox core:** No.
- **Reason:** Cloud/API-based. May offer free-tier access, but subject to billing, quotas, preview
  changes, and network availability.
- **Allowed use:** Optional proof-of-concept adapter only, disabled by default, never required for the
  app to function.

### Other Paid Cloud Providers

- Examples: ElevenLabs, OpenAI TTS, Azure Neural Voice, AWS Polly.
- **Reason not default:** Require network access and/or paid usage.
- **Allowed role:** Optional adapter only.

---

## Removed Entries

The following entries were removed because they were unverified, inaccurate, out of scope, or not
suitable for a free/local-first decision document:

- VibeVoice-Realtime-0.5B sub-80ms TTFA claim: model verified, but that benchmark was not. Upstream
  describes roughly 300 ms first audible latency.
- Fish Audio S2 / S2 Pro claims: previous size and WER figures were not verified.
- Pocket TTS: no authoritative upstream source cited — moved to "under evaluation" pending verification.
- dots.tts: no authoritative upstream source cited — moved to "under evaluation" pending verification.
- Wan Streamer v0.1 / `arXiv:2606.25041`: appears fabricated or irrelevant to a TTS utility.

---

## Required Validation Before Implementation

Before committing to any neural model implementation:

1. Generate the same sample text through each candidate.
2. Measure cold start, time to first audio, and real-time factor on the target Windows machine.
3. Measure memory and disk footprint.
4. Verify license for both inference code and model weights.
5. Confirm the model can run without paid services or mandatory network calls after installation.
