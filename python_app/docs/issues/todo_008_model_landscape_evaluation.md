# TODO #008: Evaluate Voicebox model candidates for AlienVox

**Status:** Open
**Updated:** 2026-07-27
**Scope:** Research only. No implementation yet. Candidate review for `stacks.yaml`, `src/engines/`, `setup.py`, installer packaging, and any future platform gating work.

---

## Goal

Create a single, structured evaluation pass for the most promising TTS/STT candidates surfaced in the nested `voicebox` repo, then decide which ones belong on the AlienVox roadmap.

The goal is not to implement anything yet. The goal is to gather enough real information that a smaller model can later build the right engine without having to rediscover the upstream landscape.

---

## Candidate set to evaluate

### TTS candidates

Prioritize these first:

- `Pocket TTS`
- `IndicF5`
- `VibeVoice`
- `FireRedTTS-2`
- `LongCat-AudioDiT`
- `SoproTTS`
- `NeuTTS Air / Nano`
- `dots.tts`
- `Maya1`
- `X-Voice`

Keep `VoxCPM / VoxCPM2` in a separate "blocked / watch" bucket unless platform gating or upstream CPU/MPS support improves.

### STT candidates

Also evaluate the streaming / capture-related additions surfaced in the `voicebox` roadmap:

- `Nemotron 3.5 ASR Streaming 0.6B`
- `Cohere Transcribe 03-2026`
- `ARK-ASR 3B / 0.6B`
- `IBM Granite Speech 4.1 2B / NAR`

---

## Why this matters

AlienVox already has a clear shipped set of engines, but the landscape is moving fast. We need to know:

- which models are actually usable on AlienVox's default Windows CPU-first path
- which ones need platform gating before they can be shown in the UI
- which ones are just roadmap curiosity and should stay out of the shipping catalog
- which ones have a good enough install story to justify future packaging work

This evaluation should prevent us from blindly adding a model because it looks exciting in a README.

---

## Source of information already gathered

The nested Voicebox repo already surfaces these candidates and notes:

- `docs/PROJECT_STATUS.md`
- `backend/models.py`
- `backend/voicebox-server.spec`
- `backend/backends/*.py`
- `backend/build_binary.py`

The current useful takeaway is:

- Voicebox already ships Qwen3-TTS, Qwen CustomVoice, LuxTTS, Chatterbox Multilingual, Chatterbox Turbo, TADA, and Kokoro.
- Voicebox has already evaluated and backlogged VoxCPM for CPU/MPS reasons.
- Voicebox has a curated future-model list that aligns with AlienVox's direction, especially Pocket TTS, IndicF5, VibeVoice, FireRedTTS-2, LongCat-AudioDiT, SoproTTS, NeuTTS, and dots.tts.

---

## Research questions to answer for every candidate

For each model, collect:

1. License for code
2. License for weights
3. PyPI status
4. Install command shape
5. Whether the package is git-only or needs extra download steps
6. Whether it runs on CPU
7. Whether it runs on Windows cleanly
8. Whether it runs on macOS / Apple Silicon cleanly
9. Whether it needs CUDA-only gating
10. Whether it needs special packaging hooks
11. Whether it has preset voices, cloning, or streaming
12. Whether the API is simple enough for a new `TtsEngine` subclass
13. Whether the model belongs in basic install, advanced install, or experimental-only
14. Whether it belongs in `stacks.yaml` at all

---

## Evaluation rubric

### Green

A model can move toward implementation if it satisfies most of the following:

- permissive or clearly acceptable license
- real CPU path or another first-class non-CUDA path
- installable in a way that can be reproduced in a frozen build
- no hidden preset-voice asset trap
- API is understandable without a large wrapper layer
- model purpose overlaps with AlienVox in a useful way

### Yellow

A model is still interesting, but needs one of these before it can ship:

- platform gating
- manual install instructions
- special asset provisioning
- a non-trivial packaging workaround
- a policy decision about commercial use

### Red

Keep out of the shipping catalog for now if it has any of these:

- CPU path missing or broken upstream
- Windows packaging is clearly unstable
- install requires too much bespoke patching
- the API is so awkward that it would distort AlienVox's architecture
- licensing or usage terms are too uncertain

---

## Recommended order of work

### Phase 1: Sort the list

Split everything into:

- likely worth adding
- maybe later
- not worth it

### Phase 2: Research the winners

For each likely candidate, capture:

- exact upstream repo / model card URL
- license text or authoritative summary
- install steps
- runtime requirements
- whether it fits AlienVox's dev/prod split cleanly

### Phase 3: Decide on AlienVox fit

For the short list, decide:

- `basic install`
- `advanced install`
- `experimental only`
- `do not add`

### Phase 4: Record the result

Write the final decision back into:

- `python_app/docs/issues/`
- the relevant roadmap / status doc
- any future `stacks.yaml` work queue

---

## Things to look for in the source repo

While evaluating, inspect:

- model cards and README files
- install commands and dependency pins
- whether the upstream repo expects a demo server rather than an in-process library
- whether preset voices are stored in separate repo-only assets
- whether the package has CPU, MPS, CUDA, or MLX support
- whether Windows packaging is documented or only implied

---

## Special watchouts

- Do not assume "MIT" or "Apache-2.0" on the code repo means the weights are equally permissive.
- Do not assume a streaming claim is real-time on AlienVox's CPU-default path.
- Do not assume a model with a demo server is suitable for AlienVox's in-process engine architecture.
- Do not assume a candidate belongs in `stacks.yaml` just because Voicebox mentions it.
- Do not put CUDA-only or GPU-strong models into the default experience until the platform-tier work exists.

---

## Expected output of this todo

By the end of the evaluation pass, we should have:

- a ranked candidate list
- a short note for each candidate
- a clear yes/no/maybe recommendation
- a rough implementation estimate for the likely winners
- a clear call on whether any model should be hidden behind advanced install or platform gating

---

## Done means

This todo is done when the candidate landscape is documented well enough that the next implementation task can start with no further upstream research.

