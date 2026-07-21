# TODO #006: Investigate Microsoft VibeVoice for a future engine

**Status:** Open — investigate later, not scoped/estimated yet
**Updated:** 2026-07-21
**Scope:** none yet — this is a research task, not implementation

---

## What

Look into Microsoft's VibeVoice model collection as a candidate ML engine:
https://huggingface.co/collections/microsoft/vibevoice

## Why it's on the list

VibeVoice is already name-dropped in `src/view/about.py`'s "Tech Stack" / "TTS Engines & Models"
sections ("VibeVoice-Realtime-0.5B — Streaming local TTS experiment") and in the top-level
`README.md`'s stack table, but there is **no `vibevoice_engine.py`** under `src/engines/` — it was
aspirational, never actually built. Worth checking whether it's still worth adding, given
`_ML_ENGINES` in `app_controller.py` currently only wires up Kokoro, Piper, Chatterbox, Dia,
F5-TTS, and OuteTTS.

## Things to check when picking this up

- License terms (MIT/Apache-2.0/other) — must be compatible with the project's dual-use-friendly
  stance (see `.agents/SKILLS/highlevel_design/SKILL.md`).
- Model size(s) available in the collection, and whether a small/quantized variant exists that
  fits the same "reasonable default download" bar as the other bundled models.
- Whether it runs via `transformers`/`torch` directly (fits the existing in-process, no-subprocess
  architecture) or needs something else.
- Real streaming support, since "Realtime" is in the name — if genuinely low-latency, that's a
  differentiator over the current engines and may be worth prioritizing.
- Whether the About dialog / README's existing VibeVoice mentions should be corrected (mark as
  "planned," remove, or replace with a real implementation) once a decision is made either way —
  right now they overstate what's actually implemented.

## Findings (2026-07-21, initial pass — see `explore/vibevoice` branch)

Collection has three models: `VibeVoice-1.5B`, `VibeVoice-Realtime-0.5B` (both TTS), and
`VibeVoice-ASR` (9B, not relevant here).

- **License:** MIT on both TTS models — but Microsoft's own README/model cards carry an explicit
  responsible-AI disclaimer: *"We do not recommend using VibeVoice in commercial or real-world
  applications without further testing and development... intended for research and development
  purposes only."* Legally permissive (MIT), but a real business-risk flag for a commercial
  product (AlienTech.Software) that needs a deliberate decision, not a default green light.
- **Architecture:** both are Qwen2.5 LLM backbone + σ-VAE acoustic tokenizer (3200x downsampling
  from 24kHz) + diffusion decoding head. Runs via the `transformers` library (pipeline API or
  direct `from_pretrained()`) — fits the existing in-process, no-subprocess architecture used by
  the other ML engines.
- **VibeVoice-1.5B:** Qwen2.5-1.5B backbone, 24kHz, up to 4 distinct speakers, up to ~90 min
  output, trained with context up to 65,536 tokens.
- **VibeVoice-Realtime-0.5B:** Qwen2.5-0.5B backbone, single-speaker only (explicitly not
  multi-speaker — docs point to the 1.5B model for that), ~300ms to first audible speech via a
  streaming/windowed text-encoding design. This is the one that's a genuine differentiator over
  the current engines (Kokoro/Piper/Chatterbox/Dia/F5-TTS/OuteTTS are all non-streaming,
  generate-then-play) — if the ~300ms figure holds up in practice, worth prioritizing.
- Detailed install/hardware requirements (GPU/VRAM needs, exact pip deps) weren't in the model
  card content pulled so far — next step if this moves forward is the actual GitHub repo's
  `docs/vibevoice-realtime-0.5b.md` install doc and a real local inference test.

## Real local test results (2026-07-21, `explore/vibevoice` branch)

Went past model cards — actually installed the package, downloaded weights, loaded the model, and
ran real inference in a throwaway venv (not part of this repo).

**Install is not a simple `pip install`, unlike every other engine in this project:**
- Not on PyPI. Requires `pip install "vibevoice[streamingtts] @ git+https://github.com/microsoft/VibeVoice.git"`.
- Pulls a genuinely heavy dependency set beyond torch/transformers: `aiortc` (WebRTC), `gradio`,
  `fastapi`, `uvicorn`, `av` — these are for the repo's websocket demo/server, not needed for
  simple in-process generation, but `pip install` pulls them all regardless (no lighter extra).
- Preset voices (`en-Carter_man.pt`, five other English speakers, plus ~10 other languages) are
  **not on the Hugging Face model page at all** — they're `.pt` files living only in
  `demo/voices/streaming_model/` in the GitHub repo, a separate download outside the normal
  HF-snapshot pattern every other AlienVox engine uses.
- `huggingface_hub` needs the `hf_xet` extra installed, or the plain snapshot download of
  `model.safetensors` (2.04 GB) silently corrupts/truncates and `from_pretrained()` fails with a
  confusing "does not appear to have a file named ... model.safetensors" error even though the
  file is right there. Reproduced this failure, fixed it by installing `hf_xet` first.
- The real Python API isn't `AutoProcessor`/`AutoModel` — it's the model-specific
  `VibeVoiceStreamingProcessor` + `VibeVoiceStreamingForConditionalGenerationInference` classes,
  and `generate()` needs a `cached_prompt` dict (loaded from one of those `.pt` preset files) plus
  several extra kwargs (`tts_lm_input_ids`, `tts_text_ids`, `speech_input_mask`,
  `all_prefilled_outputs`, `attention_mask`, `tts_lm_attention_mask`) with none of that
  documented on the model card — had to reverse-engineer the exact call from the GitHub demo
  script. Non-trivial to wrap into a `TtsEngine` subclass compared to the one-line
  `from_pretrained()` + `generate()` calls the current engines use.

**Confirms the "not a bug" explanation for the earlier "encoder weights not initialized" warning:**
`model.acoustic_tokenizer.encoder.*` (200+ tensors) load as random weights from
`from_pretrained()` — by design. Voice prompts for this realtime variant are precomputed KV-caches
shipped as `.pt` files, not audio encoded live through that encoder at inference time, so the
encoder path is simply unused (and untrained/unshipped) for this single-preset-voice mode.

**Real CPU performance (the actual blocker):**
- Model load: ~3s. Import: ~3-4s.
- `generate()` for a 44-char sentence ("The quick brown fox jumps over the lazy dog."): **5.54s
  wall time on CPU**, producing 3.73s of audio → **RTF = 2.53x** (i.e. took 2.53 seconds of compute
  per second of audio produced).
- This is **not real-time on CPU** — confirms the docs' own caution that only "NVIDIA T4 / Mac M4
  Pro achieve real-time performance in our tests; other devices... may require further testing."
  Since AlienVox defaults to CPU-only (`run.py`'s `--cpu` default, `_resolve_device()`), the
  headline "~200-300ms to first audio" / "Realtime" selling point does **not** hold on the
  project's own default configuration — it would need `--gpu` to actually deliver on the name.

## Recommendation

Given the install complexity (git-only, heavy unrelated deps, non-standard preset-voice download,
undocumented API) and that the core "realtime" claim doesn't hold on AlienVox's CPU-default path,
this is a **build a real `vibevoice_engine.py` before touching `setup.py`/`install_dialog.py`**
situation, not a quick win. Wiring the install-dialog/setup.py download plumbing ahead of a working
engine would surface a "Download" button for a model nothing can speak with yet.

Sequencing if this moves forward:
1. Decide on the commercial-use caveat (see above) — a business call, not a technical one.
2. Build `src/engines/vibevoice_engine.py` following the existing `TtsEngine` ABC, encapsulating
   the non-trivial `generate()` call shape found above.
3. Only then add `stacks.yaml` model entry + `setup.py` `_download_auto` mapping (weights only —
   `.pt` preset voices would need their own fetch step, not `snapshot_download()`) — the install
   dialog list is driven by `stacks.yaml`, so no separate dialog code change needed once that
   entry exists.
4. GPU-gate it in the UI (or clearly label expected CPU latency) given the RTF finding above.

## Not started

No code, no ADR, no engine module in this repo yet — everything above was tested in an isolated
throwaway venv outside the project. This is still a "look into it" placeholder pending the
commercial-use decision and the sequencing above.
