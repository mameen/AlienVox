# AlienVox Technology Options: Free and Local TTS

**Updated:** 2026-07-27  
**Project constraint:** Core TTS must be free to use or run locally. Paid cloud APIs must not be required.

This document defines the implementation options for AlienVox across all implementations. The product goal
is a lightweight cross-platform "read selected text" utility with a dependable local speech path.

See [`docs/SOTA_models.md`](SOTA_models.md) for the full model landscape, per-model verdicts, and
candidates currently under evaluation.

---

## Architecture Decision

AlienVox uses a provider-based TTS interface:

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

The application must work without an API key, billing account, or active internet connection after local
dependencies are installed.

---

## 1. What has been built (python_app)

| Engine | Stack | Model | Size | Quality | On-device | Status |
|--------|-------|-------|------|---------|-----------|--------|
| SAPI 5 | `sapi5` | OS voices | — | Medium | ✅ | **Implemented** |
| Speech Platform | `speech_platform` | MS Server v11 | — | Medium | ✅ | **Implemented** |
| Kokoro-82M | `ml/kokoro` | hexgrad/Kokoro-82M | 82 M | High | ✅ | **Implemented** |
| Piper | `ml/piper` | rhasspy/piper-voices | 30–150 MB/voice | Good | ✅ | Stub (engine TBD) |
| Chatterbox 0.5B | `ml/chatterbox` | ResembleAI/chatterbox | ~500 M | Very High | ✅ | **Implemented** |
| Dia 1.6B | `ml/dia` | nari-labs/Dia-1.6B | 1.6 B | Very High | ✅ | **Implemented** |
| F5-TTS | `ml/f5tts` | SWivid/F5-TTS | ~335 M | Very High | ✅ | **Implemented** |
| OuteTTS 0.5B | `ml/outetts` | OuteAI/OuteTTS-0.3-500M | 500 M | Good | ✅ | **Implemented** |

---

## 2. Candidate options not yet evaluated

### 2a. Accessibility / OS integrations

#### NVDA (NonVisual Desktop Access)
- **What it is:** Open-source Windows screen reader; exposes a speech API via COM.
- **Integration path:** `nvda-controller` Python library OR direct COM `nvdaController_speakText()`.
- **Pros:** Native Windows, very low latency, voices already configured by user.
- **Cons:** NVDA must be running; cannot be used standalone; accessibility-specific voices may not match
  general TTS quality expectations.
- **On-device:** ✅ (NVDA runs locally)
- **Verdict:** Low priority — use case is niche. Worth a separate ADR if accessibility becomes a priority.
- **Package:** `pip install nvda-controller` (unofficial) or direct DLL injection via `ctypes`.

#### Windows Narrator / OneCore voices
- **What it is:** Windows 10+ built-in TTS voices ("natural" voices like Aria Online).
- **Integration path:** SAPI5 already exposes these; `SpeechSynthesizer` in `System.Speech` (requires .NET
  interop).
- **Pros:** High-quality voices on Windows 11 with cloud-enhanced mode.
- **Cons:** Online variant requires internet; offline variant is the standard SAPI voice.
- **Verdict:** Already covered by SAPI5. No separate stack needed.

#### eSpeak NG
- **What it is:** Compact, formant-synthesis TTS; multilingual; very fast.
- **Package:** `pip install py-espeak-ng` (wraps the eSpeak NG binary).
- **Pros:** 100+ languages, extremely small, no GPU needed, MIT-ish licence.
- **Cons:** Robotic/synthetic quality; not competitive with neural models.
- **On-device:** ✅
- **Verdict:** Good fit as a lightweight fallback when no GPU is present. Worth an ADR.

---

### 2b. Local neural TTS (not yet added)

#### StyleTTS 2
- **Repo:** `yl4579/StyleTTS2`
- **Package:** `pip install git+https://github.com/yl4579/StyleTTS2`
- **Size:** ~300 M
- **Quality:** State-of-the-art naturalness for English; matches human in some benchmarks.
- **Voices:** Style-transfer from reference audio.
- **On-device:** ✅ (CUDA preferred; CPU possible)
- **Sample rate:** 24 kHz
- **Verdict:** High quality competitor to Chatterbox. Worth adding as `ml/styletts2`.

#### MeloTTS
- **Repo:** `myshell-ai/MeloTTS`
- **Package:** `pip install git+https://github.com/myshell-ai/MeloTTS`
- **Size:** ~200 M
- **Quality:** High, fast inference; multilingual (EN, ZH, ES, FR, JP, KR).
- **On-device:** ✅
- **Sample rate:** 44.1 kHz
- **Verdict:** Best option for multilingual support. Add as `ml/melotts`.

#### Parler-TTS Mini / Large
- **Repo:** `huggingface/parler-tts`
- **Package:** `pip install git+https://github.com/huggingface/parler-tts`
- **Size:** 880 M (Mini), 2.2 B (Large)
- **Quality:** High; description-controlled voice style ("a male voice with a warm tone").
- **On-device:** ✅ (CUDA required for real-time)
- **Sample rate:** 44.1 kHz
- **Verdict:** Unique voice-style-by-description UX. Interesting future addition.

#### Orpheus TTS
- **Repo:** `canopylabs/orpheus-tts`
- **Size:** 3B (Llama-based)
- **Quality:** Highly expressive, handles laughter/sighing/breathing.
- **On-device:** ✅ (requires ~3.5 GB VRAM on a 4090)
- **Sample rate:** 24 kHz
- **Verdict:** Best-in-class expressiveness. Slower than Kokoro; good for content production, not real-time.

#### Coqui XTTS v2
- **Package:** `pip install TTS`
- **Size:** ~2 GB
- **Quality:** Very high, 17 languages, voice cloning from 6 s reference.
- **On-device:** ✅
- **Sample rate:** 24 kHz
- **Verdict:** Mature library, well-documented. Good alternative to F5-TTS for cloning.

#### Bark (suno-ai)
- **Package:** `pip install git+https://github.com/suno-ai/bark`
- **Size:** ~5 GB (all models)
- **Quality:** Very expressive; non-verbal sounds, music.
- **On-device:** ✅ (GPU strongly preferred)
- **Cons:** Very slow (5–30× slower than Kokoro); not suitable for real-time.
- **Verdict:** Niche — good for one-shot audio production, not interactive TTS.

---

### 2c. todo_008 candidates under active evaluation

The following are surfaced from the Voicebox roadmap and are being evaluated against the rubric in
[`docs/SOTA_models.md`](SOTA_models.md). No implementation decision has been made yet.

**TTS:** Pocket TTS, IndicF5, VibeVoice, FireRedTTS-2, LongCat-AudioDiT, SoproTTS, NeuTTS Air/Nano,
dots.tts, Maya1, X-Voice

**STT:** Nemotron 3.5 ASR Streaming 0.6B, Cohere Transcribe 03-2026, ARK-ASR 3B/0.6B, IBM Granite Speech
4.1 2B/NAR

See `python_app/docs/issues/todo_008_model_landscape_evaluation.md` for full research questions and
evaluation criteria.

---

### 2d. Cloud / API TTS (excluded by design)

The following are cloud APIs and are **incompatible with AlienVox's design constraint** (no backend,
inference on-device):

| Provider | Model | Note |
|----------|-------|------|
| Google | Gemini 2.5 Flash TTS | Cloud API only; no local weights |
| Google | Cloud TTS | API |
| Azure | Azure Neural TTS | API |
| OpenAI | TTS-1 / TTS-1-HD | API |
| AWS | Polly | API |
| ElevenLabs | — | API |

These are permanently excluded unless AlienVox gains an optional cloud mode (separate ADR required).

---

## 3. ADR candidates — priority order

ADR documents live in `python_app/docs/adr/`.

| # | Title | Priority | Complexity | Value |
|---|-------|----------|------------|-------|
| ADR-005 | Add eSpeak NG as lightweight fallback engine | **MED** | Low | CPU-only fallback |
| ADR-006 | Add StyleTTS 2 as high-quality English engine | **HIGH** | Medium | Best naturalness |
| ADR-007 | Add MeloTTS for multilingual support | **HIGH** | Medium | Opens non-English |
| ADR-008 | Add Orpheus TTS for expressive/production use | MED | Medium | Expressiveness |
| ADR-009 | Add Parler-TTS description-controlled voices | LOW | Medium | Novel UX |
| ADR-010 | NVDA accessibility integration | LOW | Low | Niche audience |
| ADR-011 | Cloud TTS optional mode (Azure/Google) | LOW | High | Requires arch change |

---

## 4. Decision criteria for new engines

An engine is worth adding to AlienVox when it satisfies **all** of:

1. **On-device** — no network required for inference.
2. **Licence** — Apache 2.0, MIT, or similar (no research-only or commercial-restricted weights).
3. **Quality** — MOS ≥ 4.0 or clearly better than what is already in the stack for its use case.
4. **Install story** — `pip install <package>` + HF auto-download; no manual binary setup.
5. **Ships with tests** — `tests/test_<engine>.py` covering roster, validation guard, rate mapping, stop,
   wait_until_done.

---

## 5. Required validation before implementation

Before committing to any neural model:

1. Generate the same sample text through each candidate.
2. Measure cold start, time to first audio, and real-time factor on the target Windows machine.
3. Measure memory and disk footprint.
4. Verify license for both inference code and model weights.
5. Confirm the model runs without paid services or mandatory network calls after installation.

---

## 6. Removed / corrected claims

The following entries from earlier versions of this document were removed because they were unverified,
inaccurate, or out of scope:

- `Qwen3-TTS-rs`: repository, model figures, and latency claims were not verified.
- `any-tts`: crate and adapter claims were not verified.
- `Voxtral` as TTS: incorrect; Voxtral is speech-understanding/ASR-oriented, not a TTS engine.
- Piper "Vellum Tiny": not real Piper terminology. Use real quality tiers: `x_low`, `low`, `medium`, `high`.
- VibeVoice-Realtime-0.5B sub-80ms TTFA: model is verified, but that specific benchmark was not verified.
  Use upstream's roughly 300 ms first audible latency claim until local measurements exist.
- Rust `tts` crate as a primary integration path: relevant only to the retired `gemini_poc` implementation.
- Cloud AI voices as a high-priority product path: conflicts with the free/local requirement.
- Fish Audio S2 / S2 Pro claims: previous size and WER figures were not verified.
- Wan Streamer v0.1 / `arXiv:2606.25041`: appears fabricated or irrelevant to a TTS utility.
