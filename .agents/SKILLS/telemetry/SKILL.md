---
name: telemetry
description: Telemetry standards for AlienVox. Defines the event schema, JSONL file sink, privacy rules, session/request ID lifecycle, and what must never be logged.
license: Apache-2.0
compatibility: Universal
metadata:
  author: AlienTech.Software
  version: "1.0"
---

# Telemetry Standards

Privacy-preserving, structured telemetry for performance tuning and diagnostics. All events are written locally — no network transmission, no third-party service.

---

## 1. Sink

- **Local JSONL file**: one JSON object per line at `%LOCALAPPDATA%\com.alientech.alienvox\telemetry.jsonl` (Windows) or `~/.local/share/com.alientech.alienvox/telemetry.jsonl` (macOS/Linux).
- The file is append-only. Rotation is the user's responsibility (or a future cleanup job).
- Write failures are **silently swallowed** — telemetry must never crash or slow the app.
- Every write is flushed immediately (`flush=True`) so partial lines never appear.

---

## 2. ID Lifecycle

| ID | Generated | Scope |
| :--- | :--- | :--- |
| `session_id` | Once, at cold app startup (UUID4) | Ties all events from one app launch together |
| `request_id` | Once per speak trigger (UUID4) | Ties all events from one speak action together |

Both IDs are passed through every event so events from the same session and the same playback can be joined.

---

## 3. Event Schema

Every event is a JSON object with these fields:

```json
{
  "timestamp_unix_ms": 1721234567890,
  "event": "tts.synthesis_start",
  "session_id": "uuid4",
  "request_id": "uuid4",
  "engine": "sapi5",
  "model": "en-US-JennyNeural",
  "voice": "en-US-JennyNeural",
  "text_chars": 142,
  "text_bytes": 142,
  "latency_ms": 0,
  "status": "ok",
  "detail": null
}
```

| Field | Type | Notes |
| :--- | :--- | :--- |
| `timestamp_unix_ms` | int | Wall clock at event creation |
| `event` | string | Dot-namespaced event name (see §4) |
| `session_id` | string | UUID4, cold-start scoped |
| `request_id` | string | UUID4, per speak trigger |
| `engine` | string | Active stack name: `sapi5`, `ml`, `cloud` |
| `model` | string | Active model/voice font ID |
| `voice` | string | Selected voice ID |
| `text_chars` | int | Character count of captured text |
| `text_bytes` | int | UTF-8 byte count of captured text |
| `latency_ms` | int | ms since `speak_triggered` for latency events; 0 for others |
| `status` | string | `ok` or `error` |
| `detail` | string\|null | Error message on failure; null on success |

---

## 4. Event Names

| Event | When emitted |
| :--- | :--- |
| `app.start` | Cold app startup (no request_id yet — use empty string) |
| `app.quit` | App is quitting cleanly |
| `speak.triggered` | Global hotkey or tray menu triggered speak; text has been captured |
| `tts.synthesis_start` | Engine `speak()` called; timer starts |
| `tts.first_audio` | First audio sample delivered to output device |
| `tts.playback_end` | Playback finished (or was stopped) |
| `tts.error` | Any exception during synthesis or playback |
| `config.changed` | User changed a setting (no text fields — just engine/model/voice/key) |
| `model.install_start` | ML model download initiated |
| `model.install_end` | ML model download completed or failed |

---

## 5. Privacy Rules — Absolute

- **Never log source text.** `text_chars` and `text_bytes` are permitted; the text itself is not.
- **Never log API keys, tokens, or credentials.**
- **Never log file paths** that could reveal username or sensitive directory structure. Log model IDs, not paths.
- **Never transmit** telemetry off-device. There is no telemetry backend. If one is added in future, it requires explicit user opt-in.

---

## 6. Implementation Notes

- The telemetry module is a singleton initialized at startup with `session_id`.
- Every `speak()` call site generates a `request_id` before calling the engine and passes it through.
- Latency for `tts.first_audio` and `tts.playback_end` is computed as `now - speak_triggered_timestamp`.
- If the engine does not distinguish first-audio from playback-end (e.g., SAPI5 `Speak()` is synchronous), emit `tts.first_audio` and `tts.playback_end` at the same time with identical latency values.
- `config.changed` logs the key name that changed (e.g., `"voice"`, `"rate"`) but not the old or new value.
