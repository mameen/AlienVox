# TODO #001: Local TTS Stack Implementation

**Status:** Open  
**Created:** 2026-07-18  
**Component:** `gemini_poc`, local TTS engines, ML/AI dev path  

## Summary

AlienVox now has a compiling Rust/Tauri app with Windows SAPI speech and a dev-testable Kokoro ML/AI bridge. The remaining work is to turn the current proof-of-concept into a reliable local-first TTS stack.

## Current State

- Windows SAPI backend compiles and supports speak, stop, pause, resume, voice enumeration, rate, pitch, and volume.
- The ML/AI tab is enabled in the frontend.
- The ML/AI path routes to a local Kokoro dev runner through `gemini_poc/.venv`.
- Kokoro dependencies and model cache are installed locally for the current dev environment.
- Model cache is ignored under `gemini_poc/.models/`.
- Cloud TTS is documented as optional/demo only and not part of the core path.

## Remaining Work

1. Replace the process-based Kokoro dev bridge with a production-ready local engine strategy.
   - Decide whether the next implementation target is Python sidecar, ONNX Runtime, Candle, or another native path.
   - Keep deployment concerns aligned with ADR-003.

2. Implement real selected-text capture.
   - Replace the Windows placeholder in `capture_win.rs`.
   - Support UI Automation first, then clipboard fallback.
   - Preserve the privacy rule: do not log captured text.

3. Route tray actions through real commands.
   - `Speak Selection` should capture the active selection and speak it.
   - `Stop` should stop both native and ML playback.

4. Add durable engine selection.
   - Persist selected engine, voice, rate, pitch, and volume.
   - Keep native OS TTS as the fallback if ML/AI is unavailable.

5. Improve ML/AI runtime status reporting.
   - Show whether Kokoro dependencies are installed.
   - Show whether model files/cache are available.
   - Provide a local setup/download action or clear manual setup path.

6. Add local benchmark checks.
   - Measure cold start.
   - Measure time to first audio.
   - Measure memory use.
   - Compare SAPI, Kokoro, and VibeVoice-Realtime-0.5B before changing defaults.

7. Add focused tests or smoke checks.
   - Rust compile check.
   - Voice enumeration smoke check.
   - ML/AI runner dependency check.
   - Direct Kokoro synthesis smoke check in the dev environment.

## Resolved Documentation Cleanup

`issue_002.md` was resolved by updating the technology docs:

- Removed fabricated or unverified model recommendations from the active decision path.
- Corrected Piper terminology.
- Treated Gemini/cloud TTS as optional/demo only.
- Reintroduced VibeVoice-Realtime-0.5B as a verified MIT/local-capable experimental candidate while removing the unverified sub-80ms claim.
