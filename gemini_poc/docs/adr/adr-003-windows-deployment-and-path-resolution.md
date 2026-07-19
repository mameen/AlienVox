# Architecture Decision Record (ADR)
## ADR-003: Windows Deployment Model and Unified Path Resolution

| Attribute | Specification |
| :--- | :--- |
| **Status** | Accepted (gemini_poc scope only) |
| **Date** | July 15, 2026 |
| **Author** | Principal Architect |
| **Project Context** | AlienVox — gemini_poc POC (AlienTech.Software) |

---

## Context and Problem Statement

AlienVox is evolving from a single native-engine (SAPI) prototype toward a multi-stack
architecture where separate TTS engines (SAPI, Microsoft Speech Platform, and neural
ML/AI models) are selected via user Preferences. Neural stacks require model files
(e.g. Piper, Kokoro-82M) that must live somewhere on disk and, in some cases, be
downloaded after installation.

This forces two questions that must be answered before any neural backend is written:

1. **How is the app deployed on Windows, and where does it install?** The install
   location determines whether the process can write files (e.g. downloaded models)
   at runtime without administrator elevation.
2. **How are on-disk assets located reliably?** The current tray icon resolves its
   path via the compile-time macro `env!("CARGO_MANIFEST_DIR")`. This only works on
   the build machine; in a shipped binary that path does not exist, so asset loading
   fails on any other computer. Every path (`.models`, config, icons) needs a single,
   deployment-safe resolution strategy that behaves identically in dev and production.

---

## Decision

### 1. Installer Target — NSIS (Per-User)

Standardize on Tauri's default **NSIS per-user** installer.

- Installs into `%LOCALAPPDATA%\AlienVox\` instead of the admin-locked
  `C:\Program Files\`.
- Standard users can write to the install tree without UAC prompts.
- Downloaded models still resolve to a dedicated writable data folder (see §4) so
  application updates and uninstalls remain clean and never wipe user models.

MSI/per-machine is explicitly **not** the primary target; its read-only Program Files
location would block runtime model downloads for standard users.

### 2. Distribution Payload — Zero-Model Default with User Drop-In

Ship a **lightweight launcher installer** (~10–15 MB) with **no bundled neural models**.

- Out of the box the app uses the native platform engine (SAPI 5 / WinRT), which
  requires no shipped assets.
- The Preferences UI lets the user **download** a neural model or **drag-and-drop** a
  `.onnx` file into their local writable model folder.
- Rationale: bundling Kokoro-82M (~330 MB) or VibeVoice-0.5B (~1.0 GB) would balloon
  the installer. Keeping the base distribution small preserves the standalone,
  efficient-footprint goals of ADR-002.

### 3. Unified Path Resolution Utility (`paths.rs`) — Build First

Introduce a single path-resolution module **before** the neural backend, and migrate
existing callers (including the tray icon) onto it.

- Uses Tauri's runtime path API — `app.path().app_local_data_dir()` and
  `app.path().resource_dir()` — rather than compile-time or hardcoded paths.
- Removes the `env!("CARGO_MANIFEST_DIR")` tray-icon dependency, which is a latent
  crash on any non-build machine.
- Guarantees assets, configuration, and `.models` resolve identically in
  `cargo tauri dev` and in a deployed binary.

### 4. `.models/` Directory Search Order

The model resolver searches these locations in priority order and merges results:

| Priority | Purpose | Path |
| :--- | :--- | :--- |
| 1 | Writable local app data (primary — downloaded models) | `%LOCALAPPDATA%\com.alientech.alienvox\.models\` |
| 2 | Bundled app resources (only if we pre-ship models) | `%LOCALAPPDATA%\AlienVox\resources\.models\` |
| 3 | Local dev override (Cargo dev environment) | `C:\dev\tts\gemini_poc\.models\` |

Notes:
- Priority 1 uses the **bundle identifier** (`com.alientech.alienvox`) via
  `app_local_data_dir()`; this is where the "Download"/drop-in flow writes.
- Priority 2 uses the **product name** (`AlienVox`) install tree via `resource_dir()`;
  read-only, reserved for any future pre-shipped models.
- Priority 3 exists only for developer iteration and is never present in a shipped app.
- Each stack owns a subfolder, e.g. `.models\piper\`, `.models\kokoro\`, so the layout
  is self-describing and Preferences can point each engine at its own subtree.

---

## Consequences

### Benefits
- **No elevation friction**: per-user install + per-user model folder means model
  downloads never trigger UAC or access-denied failures.
- **Small distribution**: launcher installer stays lightweight; large models are opt-in.
- **Dev/prod parity**: one resolver removes an entire class of "works on my machine"
  path bugs, and fixes the existing tray-icon defect.
- **Clean updates**: user models in app-data survive reinstalls and version upgrades.

### Trade-offs
- **Per-user scope**: an NSIS per-user install is not shared across Windows accounts;
  each user reinstalls and re-downloads models. Acceptable for a personal utility.
- **First-run download step**: neural voices require an explicit user action before
  first use, rather than working immediately from the box.
- **Migration cost**: existing code paths using `CARGO_MANIFEST_DIR` must be refactored
  onto `paths.rs` before feature work proceeds.

---

## Related Decisions
- [ADR-001](./adr-001.md) — Rust + Tauri core tech stack.
- [ADR-002](./adr-002-tauri-production-build.md) — Single standalone binary production build.
- [ADR-004](./adr-004-tts-stack-architecture.md) — Multi-stack TTS engine architecture.
