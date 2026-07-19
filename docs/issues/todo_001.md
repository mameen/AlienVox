# TODO #001: Local TTS Stack Implementation

**Status:** Open  
**Created:** 2026-07-18  
**Component:** `gemini_poc`, local TTS engines, ML/AI dev path  

## Summary

AlienVox now has a compiling Rust/Tauri app with Windows SAPI speech, a dev-testable warm Kokoro ML/AI bridge, and a local Piper fallback. The remaining work is to turn the current proof-of-concept into a reliable local-first TTS stack.

## Current State

- Windows SAPI backend compiles and supports speak, stop, pause, resume, voice enumeration, rate, pitch, and volume.
- The ML/AI tab is enabled in the frontend.
- The ML/AI path routes to local Python dev runners through `gemini_poc/.venv`.
- ML/AI playback exposes a configurable hot-model TTL, defaulting to 30 seconds.
- Kokoro direct playback currently uses that TTL through its persistent warm worker.
- Piper `en_US-lessac-medium` is installed under `gemini_poc/.models/ml/piper` as a fast offline fallback.
- The UI lists Kokoro, Piper, VibeVoice-Realtime-0.5B, ZONOS2, and Dia; only installed local models are playable.
- Engine, model, voice, rate, pitch, and volume choices persist in local storage.
- The temporary menu is hidden; unimplemented toolbar actions are disabled; Save is exposed as Export WAV.
- ML model install actions are routed separately from Windows voice installation.
- Installers are wired for Kokoro, Piper, VibeVoice-Realtime-0.5B, ZONOS2, and Dia, writing local assets under the resolved `.models/ml` root.
- Voice/model installs use an in-app confirmation dialog; ML installs run as cooperative jobs with polling progress and cancellation.
- New/Open/Save are document actions for text-oriented source files, while Convert to Audio exports WAV.
- Tab panes reclaim space from irrelevant stack-specific controls; for example, native SAPI tabs hide the ML model selector instead of disabling it.
- Local JSONL telemetry records generated session/play ids, engine/model/voice, text size, full stack configuration, trigger-to-first-audio latency, playback end where observable, and errors without recording source text.
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

4. Improve durable engine selection.
   - Persist settings outside browser local storage if/when the UI becomes production settings.
   - Keep native OS TTS as the fallback if ML/AI is unavailable.

5. Improve ML/AI runtime status reporting.
   - Show whether Kokoro dependencies are installed.
   - Show whether model files/cache are available for each model.
   - Provide a local setup/download action or clear manual setup path.

6. Add local benchmark checks.
   - Measure cold start.
   - Measure time to first audio.
   - Measure memory use.
   - Compare SAPI, Kokoro, Piper, and VibeVoice-Realtime-0.5B before changing defaults.

7. Add focused tests or smoke checks.
   - Rust compile check.
   - Voice enumeration smoke check.
   - ML/AI runner dependency check.
   - Direct Kokoro and Piper synthesis smoke checks in the dev environment.
   - Telemetry smoke check that verifies `tts.requested`, `tts.first_audio`, and `tts.playback_end` for ML direct playback.

8. Implement the next SOTA candidates from the docs.
   - Benchmark VibeVoice-Realtime-0.5B next because it is the most relevant open local streaming candidate.
   - Keep ZONOS2 and Dia listed as experimental until local setup, hardware requirements, and quality/performance are verified.
   - Add playback/export runtime adapters after model installation succeeds; installers only fetch local model assets.

## Resolved Documentation Cleanup

`issue_002.md` was resolved by updating the technology docs:

- Removed fabricated or unverified model recommendations from the active decision path.
- Corrected Piper terminology.
- Treated Gemini/cloud TTS as optional/demo only.
- Reintroduced VibeVoice-Realtime-0.5B as a verified MIT/local-capable experimental candidate while removing the unverified sub-80ms claim.
