# Architecture Decision Record (ADR)
## ADR-004: Multi-Stack TTS Engine Architecture

| Attribute | Specification |
| :--- | :--- |
| **Status** | Accepted |
| **Date** | July 15, 2026 |
| **Author** | Principal Architect |
| **Project Context** | AlienVox (AlienTech.Software) |

---

## Context and Problem Statement

AlienVox must support several independent TTS **stacks** — classic SAPI 5, the Microsoft
Speech Platform, cross-platform neural ML/AI models, and (later) high-level library
bridges such as the `tts` / `any-tts` crates. The testing harness already exposes these
as engine tabs; the shipped app will expose them through Preferences.

These stacks differ fundamentally: SAPI is Windows-only COM (`ISpVoice`), synthesizes
and plays audio itself, and — critically — is `!Send`, so it is owned by a dedicated STA
thread and driven through an `mpsc` channel. Neural stacks are cross-platform and must
build their own pipeline (G2P → ONNX inference → PCM playback). Despite this, the app
needs **one uniform way** to enumerate voices, speak with prosody control, pause/resume,
stop, and switch the active stack. This ADR defines that abstraction.

---

## Decision

### 1. Uniform `TtsEngine` Trait

Every stack implements a single object-safe trait, stored as `Box<dyn TtsEngine + Send>`.
Engines use **interior mutability** (channel / STA thread), so methods take `&self`.

```rust
use std::path::Path;
use anyhow::Result;

/// A selectable voice: stable `id` for selection, `name` for display.
pub struct Voice { pub id: String, pub name: String }

/// Prosody the UI controls; a field is ignored by engines that lack support.
pub struct SpeakParams { pub rate: i32, pub pitch: i32, pub volume: u8 }

pub trait TtsEngine {
    fn list_voices(&self) -> Result<Vec<Voice>>;
    fn speak(&self, text: &str, voice_id: &str, params: &SpeakParams) -> Result<()>;
    fn pause(&self) -> Result<()>;
    fn resume(&self) -> Result<()>;
    fn stop(&self) -> Result<()>;
}
```

### 2. Voice Identity — id vs. name

`list_voices` returns `Voice { id, name }`, never bare strings. Selection is always by
the **stable id** (SAPI token id, or model file path), because display names collide and
are not stable. This preserves the existing `VoiceInfo { id, name }` contract already used
by the frontend dropdown.

### 3. Prosody Is First-Class

`speak` takes `SpeakParams { rate, pitch, volume }`. The UI already sends these and SAPI
honors them; engines that cannot map a field simply ignore it. Pause/resume are explicit
trait methods (SAPI supports them and the toolbar exposes them).

### 4. `ActiveStack` Selector — Aligned to the UI

The selected stack is a serde enum whose variants match the frontend tab `data-engine`
keys, so the same string flows UI → command → Preferences persistence unchanged.

```rust
#[derive(Clone, Copy, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActiveStack {
    Sapi5,          // Windows only
    SpeechPlatform, // Windows only
    Ml,             // cross-platform (ort + rodio + espeak)
    Library,        // future: `tts` / `any-tts` bridge
}
```

Stack **availability is platform-dependent** — SAPI variants do not exist on macOS — so
the stack registry filters variants per target OS (`cfg`), and `sapi4` remains a disabled
placeholder (dead API, not enumerable).

### 5. Source Layout — One Folder per Stack

```
src/
├── paths.rs            # ADR-003 resolver (models dirs, resources, app data)
└── engines/
    ├── mod.rs          # TtsEngine trait, Voice, SpeakParams, ActiveStack, registry
    ├── sapi/           # Windows-only (cfg-gated); adapts existing audio_win.rs
    ├── ml/             # cross-platform: ort (ONNX) + rodio (playback) + espeak (G2P)
    └── library/        # future high-level bridge
```

The ML engine receives its model directories **at construction** from the ADR-003
resolver — `models_dir` is deliberately **not** a trait parameter, keeping the SAPI/registry
stacks free of a concern they don't have. Each stack owns a `.models/<stack>/` subfolder
(see ADR-003 §4).

### 6. Error Handling and Threading Constraints

- Engines use `anyhow::Result` internally; Tauri commands convert to `Result<_, String>`
  at the IPC boundary.
- The trait object must be `Send`. SAPI's `ISpVoice` is `!Send`, so its implementation
  holds only the `mpsc::Sender` to the STA thread (which is `Send`) — the pattern already
  in `audio_win.rs`.

---

## Consequences

### Benefits
- **Uniform call site**: commands and Preferences treat every stack identically.
- **Extensible**: adding a stack means one trait impl + one enum variant + one folder.
- **No capability loss**: id/name, prosody, and pause/resume all survive the abstraction.
- **Bridge-pattern intact**: OS-specific stacks stay `cfg`-gated; neural stack is shared.

### Trade-offs
- **Lowest-common-denominator trait**: engine-specific features (e.g. SAPI XML, neural
  voice cloning) need capability extensions beyond the base trait.
- **New dependency**: `anyhow` is introduced for the internal engine layer.
- **Refactor cost**: existing `audio_win.rs` must be adapted to implement the trait.

---

## Related Decisions
- [ADR-001](./adr-001.md) — Rust + Tauri core tech stack.
- [ADR-002](./adr-002-tauri-production-build.md) — Single standalone binary production build.
- [ADR-003](./adr-003-windows-deployment-and-path-resolution.md) — Deployment model and path resolution (`.models` search order).
