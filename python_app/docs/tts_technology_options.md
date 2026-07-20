# TTS Technology Options

**Last updated:** 2026-07-20  
**Status:** Living document — updated as engines are added or evaluated

---

## 1. What we have built

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
- **Cons:** NVDA must be running; cannot be used standalone; accessibility-specific voices may not match general TTS quality expectations.
- **On-device:** ✅ (NVDA runs locally)
- **Verdict for ADR:** Low priority — use case is niche (screen-reader users who also want AlienVox). Worth a separate ADR if accessibility becomes a priority.
- **Package:** `pip install nvda-controller` (unofficial) or direct DLL injection via `ctypes`.

#### Windows Narrator / OneCore voices
- **What it is:** Windows 10+ built-in TTS voices ("natural" voices like Aria Online).
- **Integration path:** SAPI5 already exposes these; `SpeechSynthesizer` in `System.Speech` (requires .NET interop).
- **Pros:** High-quality voices on Windows 11 with cloud-enhanced mode.
- **Cons:** Online variant requires internet; offline variant is the standard SAPI voice.
- **Verdict:** Already covered by SAPI5 tab. No separate stack needed.

#### eSpeak NG
- **What it is:** Compact, formant-synthesis TTS; multilingual; very fast.
- **Package:** `pip install py-espeak-ng` (wraps the eSpeak NG binary).
- **Pros:** 100+ languages, extremely small, no GPU needed, MIT-ish licence.
- **Cons:** Robotic/synthetic quality; not competitive with neural models.
- **On-device:** ✅
- **Verdict for ADR:** Good fit as a lightweight fallback when no GPU is present. Worth an ADR.

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
- **Verdict for ADR:** High quality competitor to Chatterbox. Worth adding as `ml/styletts2`.

#### MeloTTS
- **Repo:** `myshell-ai/MeloTTS`
- **Package:** `pip install git+https://github.com/myshell-ai/MeloTTS`
- **Size:** ~200 M
- **Quality:** High, fast inference; multilingual (EN, ZH, ES, FR, JP, KR).
- **On-device:** ✅
- **Sample rate:** 44.1 kHz
- **Verdict for ADR:** Best option for multilingual support. Add as `ml/melotts`.

#### Parler-TTS Mini / Large
- **Repo:** `huggingface/parler-tts`
- **Package:** `pip install git+https://github.com/huggingface/parler-tts`
- **Size:** 880 M (Mini), 2.2 B (Large)
- **Quality:** High; description-controlled voice style ("a male voice with a warm tone").
- **On-device:** ✅ (CUDA required for real-time)
- **Sample rate:** 44.1 kHz
- **Verdict for ADR:** Unique voice-style-by-description UX. Interesting future addition.

#### Orpheus TTS
- **Repo:** `canopylabs/orpheus-tts`
- **Size:** 3B (Llama-based)
- **Quality:** Highly expressive, handles laughter/sighing/breathing.
- **On-device:** ✅ (4090: ~3.5 GB VRAM)
- **Sample rate:** 24 kHz
- **Verdict for ADR:** Best-in-class expressiveness. Slower than Kokoro; good for content production.

#### Coqui XTTS v2
- **Package:** `pip install TTS`
- **Size:** ~2 GB
- **Quality:** Very high, 17 languages, voice cloning from 6 s reference.
- **On-device:** ✅
- **Sample rate:** 24 kHz
- **Verdict for ADR:** Mature library, well-documented. Good alternative to F5-TTS for cloning.

#### Bark (suno-ai)
- **Package:** `pip install git+https://github.com/suno-ai/bark`
- **Size:** ~5 GB (all models)
- **Quality:** Very expressive; non-verbal sounds, music.
- **On-device:** ✅ (4090: fits comfortably)
- **Cons:** Very slow (5–30× slower than Kokoro); not suitable for real-time.
- **Verdict for ADR:** Niche — good for one-shot audio production, not interactive TTS.

---

### 2c. Cloud / API TTS (excluded by design)

The following are cloud APIs and are **incompatible with AlienVox's design constraint** (no backend, inference on-device):

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
2. **Licence** — Apache 2.0, MIT, or similar (no research-only).
3. **Quality** — MOS ≥ 4.0 or clearly better than what's already in the stack for its use case.
4. **Install story** — `pip install <package>` + HF auto-download; no manual binary setup.
5. **Ships with tests** — `tests/test_<engine>.py` covering roster, validation guard, rate mapping, stop, wait_until_done.

---

## 5. Notes on Piper stub

`piper_win.py` is currently a stub returning `b""`. Piper is a fast, high-quality neural TTS that runs on CPU — useful as a lightweight alternative to Kokoro when GPU is unavailable. The implementation requires:

- ONNX runtime (`pip install onnxruntime`)
- Per-voice `.onnx` + `.onnx.json` files (already downloadable via the Install dialog)
- `piper-phonemize` for phonemisation

See `todo_002.md` for the full implementation task.
