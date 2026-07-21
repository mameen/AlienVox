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

## Not started

No code, no ADR, no engine module. Research so far is model-card-level only (no local install/test
yet). This is still a "look into it" placeholder pending a decision on the commercial-use caveat
above.
