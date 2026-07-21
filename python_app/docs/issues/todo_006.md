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

## Not started

No code, no ADR, no engine module. This is purely a "look into it" placeholder.
