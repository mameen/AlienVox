# Issue #002: Unverified / Inaccurate TTS Model Claims in Technology Docs

**Status:** Open  
**Priority:** Medium  
**Created:** 2026-07-14  
**Component:** `docs/SOTA_models.md`, `docs/tts_technology_options.md`  

---

## Summary

A review of the two TTS technology reference docs found a mix of verified entries
and claims that are unverified or likely inaccurate. The native OS engine sections
and the two primary edge models are sound; several ML-model entries need upstream
verification before the docs are treated as authoritative.

### Verified (safe to rely on)
- Windows native engines: SAPI 4/5, Microsoft Speech Platform, WinRT `SpeechSynthesizer`.
- macOS native: `AVSpeechSynthesizer`, Personal Voice (macOS 14+).
- **Kokoro-82M** — Apache 2.0, ~330MB, StyleTTS2 + ISTFTNet.
- **Zonos** (Zyphra), **Dia** (Nari Labs, 1.6B), **FireRedTTS-2** — real projects.
- The `tts` crate (§4A) — cross-platform native backend bridge (Tolk/WinRT, AVFoundation, Speech Dispatcher).

### Needs verification or correction

| Doc | Entry | Concern |
|---|---|---|
| `tts_technology_options.md` | Piper (§3C) | "Vellum Tiny (~15MB)" is not real Piper terminology; voice tiers are `x_low / low / medium / high`. |
| `tts_technology_options.md` | Qwen3-TTS-rs (§3B) | `second-state/qwen3_tts_rs` repo and ~97ms / 0.6B figures unconfirmed. |
| `tts_technology_options.md` | `any-tts` crate (§4B) | Crate existence on crates.io unconfirmed; listing **Voxtral** as a TTS adapter is wrong (Voxtral is a speech-understanding/ASR model, not TTS). |
| `SOTA_models.md` | Fish Audio S2 (§2A) | "4B / S2 Pro" size and WER (0.54% / 0.99%) figures likely overstated; verify against `fishaudio/fish-speech`. |
| `SOTA_models.md` | VibeVoice-Realtime-0.5B (§1B) | Microsoft VibeVoice is real (1.5B); a "Realtime-0.5B / sub-80ms TTFA" variant is unverified naming. |
| `SOTA_models.md` | Pocket TTS (§3A), dots.tts (§3B) | No repositories cited; existence as described is unconfirmed. |
| `SOTA_models.md` | Wan Streamer v0.1 (§4A) | Appears **fabricated**: "Wan" is Alibaba's *video* model line, `arXiv:2606.25041` is malformed/implausible, and a unified omni-modal transformer is out of scope for a TTS utility. |

---

## Required Actions

1. Verify each flagged entry against its upstream repository / paper.
2. Correct figures and naming, or remove entries that cannot be substantiated.
3. Strongly consider removing "Wan Streamer v0.1" unless a real source is produced.
4. Keep **Kokoro-82M** (default, CPU, Apache 2.0) and **Piper** (MIT, ultra-light fallback)
   as the primary local-model targets.

---

## Notes

The docs have been annotated with a verification-status callout linking back to this
issue. This issue tracks the follow-up verification work; it does not itself edit the
model claims.
