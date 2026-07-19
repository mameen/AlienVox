---
name: cross-platform-development
description: Guidelines for implementing cross-platform desktop modules using the Bridge pattern. Enforces strict OS isolation, anti-mocking test state philosophies, and absolute adherence to intent without shortcuts.
license: Apache-2.0
compatibility: Cross-platform environment (Windows 11 / macOS 14+)
metadata:
  author: AlienTech.Software
  version: "1.0"
---

# Cross-Platform Architecture & Development Guidelines

This skill codifies the architectural, structural, and testing standards required to build low-latency, deterministic, cross-platform components for AlienTech.Software projects (such as AlienVox)[cite: 3, 4, 5]. It is especially aligned with the repo's selected stack: **Rust + Tauri** for the core application runtime.

## 1. Core Principles

### Factory Owner, Not Coder
- **Anchor to Intent:** Your goal is to express and fulfill the developer's exact stated intent. If instructions or requirements are ambiguous, you must stop and ask; never silently infer context.
- **Zero Shortcuts:** You are strictly forbidden from taking shortcuts, collapsing multiple complex tasks into single compromises, or skipping steps because an implementation is complex. Keeping an application simple means executing clean, unbloated designs—it *never* means delivering an incomplete, cut-corner, or incorrect feature.
- **Surface Assumptions:** Explicitly state what you are about to assume and wait for user confirmation before executing any code changes.

### Anti-Mocking Testing Philosophy
- **Real Code Execution:** Mocking dependencies is strongly discouraged. Unit tests and functional integration pipelines must execute actual, deterministic code branches against real buffers wherever possible.
- **Concrete Test Data:** Provide explicit, real-world mock data files, clipboard structures, or memory state vectors to test the genuine logic of the **Rust + Tauri** application rather than simulating structural responses through arbitrary mock interfaces.

---

## 2. Structural Patterns: The Bridge & Suffix Isolation

Every system-level subsystem must be separated into a platform-agnostic abstract contract layer and isolated, platform-specific concrete implementations.

### 2.1 File Suffix Mapping Rules
For standalone or lightweight structural integrations, use strict suffix tracking:
- `*._core.*` / `*._base.*` — Contains the common interface/trait definition. Absolutely no platform imports allowed.
- `*_win.*` — Isolated platform execution for Windows 11 (Win32, COM, UI Automation APIs).
- `*_mac.*` — Isolated platform execution for macOS 14+ (Cocoa, AppKit, AVFoundation APIs).
- `*_lnx.*` — Isolated platform execution for Linux kernels (X11, Wayland, DBus).

### 2.2 Subsystem Directory Isolation
For intricate multi-file pipelines (e.g., local OCR engines or native accessibility tree scrapers), separate modules inside platform-specific child directories managed by a top-level dispatcher:

```text
services/<subsystem-name>/
├── mod.rs                   # Directs compilation dynamically based on target_os
├── interface.rs             # Houses the abstract traits or shared definitions
├── win/                     # Fully cordoned Windows logic paths
│   └── text_grabber.rs
└── mac/                     # Fully cordoned macOS logic paths
    └── text_grabber.rs
```

---

## 3. Tauri Production Build Architecture — Single Standalone Binary

### 3.1 Clarification: No Runtime Server

Developers unfamiliar with Tauri's architecture may incorrectly assume that AlienVox depends on an external Node.js or HTTP server at runtime. The `cargo tauri dev` command starts a local development server for hot-reloading UI code, which creates confusion about the production deployment model. This section explicitly clarifies how Tauri produces a **single, standalone binary** with zero runtime server dependencies.

### 3.2 How Tauri Produces a Single Standalone Binary

Tauri's production build pipeline (`cargo tauri build`) ensures AlienVox ships as a single, self-contained executable through two mechanisms:

#### Inlining the Frontend
During the production build phase:
- The frontend (HTML, CSS, TypeScript/JavaScript) is compiled, bundled, and minified.
- Tauri embeds these assets directly into the compiled Rust binary using Rust's `include_bytes!` macro mechanism.
- The frontend exists as raw byte assets inside the binary — not as separate files on disk.

#### Zero-Network IPC (Inter-Process Communication)
Because the frontend is embedded:
- No HTTP server runs at runtime. The `localhost:3000` dev server does **not** exist in production.
- Tauri boots the OS's native webview container:
  - **WebView2** (Microsoft Edge Chromium) on Windows
  - **WebKit** on macOS
- The embedded HTML loads directly from memory into the webview process.
- Communication between the UI layer and Rust backend uses Tauri's native OS-level IPC bridge — not HTTP endpoints.

### 3.3 Development vs. Production Summary

| Phase | What Happens Behind the Scenes | Is There a Server? |
| :--- | :--- | :--- |
| **Development**<br>`cargo tauri dev` | A temporary, local-only tooling process hosts TypeScript/HTML files so UI changes mirror instantly without forcing a full Rust re-compilation. | **Temporarily — yes**<br>Local host process strictly for the developer's machine only. |
| **Production**<br>`cargo tauri build` | TypeScript and HTML files are baked directly into the `.exe` (Windows) or `.app` (macOS) binary alongside Rust code. | **No**<br>Completely self-contained, standalone desktop binary. Zero server dependencies. |

### 3.4 Consequences

#### Benefits
- **Deployment Simplicity:** Single executable per platform — no installers, no runtime prerequisites (other than OS webview components which ship with all modern Windows 11 / macOS 14+ systems).
- **No Runtime Server Overhead:** Zero memory or CPU cost for a dev server process. All resources contribute to the sub-10MB idle footprint goal.
- **Security:** No HTTP listeners mean no risk of network-based attacks targeting a local development server.
- **Predictable Behavior:** The app behaves identically in development and production — frontend always loads from binary, never from a network port.

#### Trade-offs
- **Longer Iteration Time During Development:** UI changes require full `cargo tauri build` cycles if not using `cargo tauri dev`. Developers must use the dev server for productive UI iteration.
- **Binary Size:** Embedded frontend assets increase binary size slightly (typically 2–5 MB depending on UI complexity).

---

## 4. Single-Application Runtime & Model Integration

### 4.1 One Application — Non-Negotiable
AlienVox **MUST** ship as one application. Because Rust + Tauri compiles to a single standalone binary (see Section 3), the Win32 native hooks, the LLM/TTS integration layer, and the optional settings webview all live in one codebase and one executable per platform. There is no separate backend process, sidecar server, or second build system. Any design that splits the runtime into multiple applications violates this rule.

### 4.2 Rust as the Model-Calling Runtime
Rust is the runtime that calls all LLM and TTS models directly, in-process. Python remains confined to bootstrapping and developer tooling and is never part of the runtime path. Models are integrated through one of two paths:

#### Path A — Cloud / Remote Models
- Hosted LLM and TTS providers (e.g., OpenAI, ElevenLabs, Azure) are HTTPS REST/streaming APIs.
- Call them from Rust with an async HTTP client (`reqwest` + `tokio`), consuming streamed audio chunks to preserve low latency.
- API keys resolve from native system environment variables or `.gitignore`-d local files — never hard-coded or committed.

#### Path B — Local / Open-Source ML TTS Models
Open-source neural TTS models are typically published as Python (PyTorch) artifacts. Rust **cannot** import a raw Python checkpoint at runtime, so local models are integrated exclusively through one of:
- **ONNX Runtime via the `ort` crate** — export the model to ONNX and run inference in-process (e.g., Piper-style TTS). Preferred default.
- **`candle`** — HuggingFace's pure-Rust ML framework for models that run natively without Python.
- **Bundled native inference binary** — a compiled engine driven from Rust.

#### Native OS TTS Fallback
Local, zero-dependency speech via the platform's built-in engine is the fastest fallback and must be available:
- **Windows:** SAPI / WinRT through the `windows` crate.
- **macOS:** AVFoundation / `NSSpeechSynthesizer` via the `mac` platform path.

### 4.3 Constraint Summary
- "Call other TTS models from inside the app" means ONNX-exported or natively-compiled models — never embedded Python.
- The model-integration layer follows the Bridge & suffix isolation rules of Section 2 like any other subsystem.

---

## 5. Configuration — One-Way Data Flow (see also: ADR to be recorded)

Every configurable setting in AlienVox is owned by a YAML descriptor on disk. The
engine layer, the UI, and telemetry all **read** from the merged config; user input
**writes** back to the config file and the app reloads. No code path mutates engine
state, UI widgets, or persisted values out-of-band. This keeps state single-sourced,
diffable, and testable without a running app.

### 5.1 Read / Write Directions

- **Read (fan-out)**: YAML → engine construction, YAML → UI control rendering, YAML → telemetry stack configuration.
- **Write (single sink)**: user input → YAML file → reload → fan-out again.
- The UI **must not** hard-code model-specific fields (voice lists, rate/pitch ranges, install manifests). If a knob isn't declared in YAML, it isn't rendered. Adding a new model means dropping a folder with `model.yaml` — no Rust or frontend edits.
- The engine **must not** cache setting values past a reload. Every `speak` reads the effective config for the current stack/model/voice.

### 5.2 Four-Layer Config Hierarchy

Later layers override earlier ones. The resolver merges bottom-up and hands the
flattened view to both the engine and the UI.

| # | Layer | Location | Purpose |
| :--- | :--- | :--- | :--- |
| 1 | Built-in defaults | Compiled into the engine | Baseline values so a missing YAML never crashes the app. |
| 2 | Stack config | `.models/<stack>/stack.yaml`, `.apis/<provider>/provider.yaml` | Stack- or provider-wide settings (default TTL, models root, API base URL, auth env-var name). |
| 3 | Model / voice config | `.models/<stack>/<model>/model.yaml` | Per-model knobs, voice roster, install manifest, UI hints (control ranges, labels, which sliders apply). |
| 4 | User overrides | `%LOCALAPPDATA%\<identifier>\user.yaml` (per ADR-003 §4·1) | Last-picked engine/model/voice, slider values, hotkey binding — the persisted UI state. |

### 5.3 Concrete Paths

- Stacks live under `.models/<stack>/` (matches ADR-004 §5 folder layout).
- Cloud providers live under `.apis/<provider>/` alongside `.models`.
- All paths resolve through the ADR-003 `paths.rs` search order (`app_local_data_dir` → `resource_dir` → dev override). The config resolver reuses that search order — it does **not** invent its own path scheme.
- Secrets referenced by `provider.yaml` (API keys) resolve from OS environment variables named in the YAML; the key value is never written into any YAML on disk (per `workspace-discipline` §2 secret cordoning).

### 5.4 UI Hint Schema (informative)

Model YAML declares what the UI should render, so the frontend is a generic renderer:

```yaml
# .models/ml/kokoro/model.yaml (illustrative)
id: kokoro
name: Kokoro-82M
runtime: python-worker           # engine chooses adapter
adapter: dev/kokoro_worker.py
voices:
  - { id: af_heart, label: "American F · Heart" }
  - { id: bm_george, label: "British M · George" }
controls:
  rate:   { min: -10, max: 10, default: 0, applies: true }
  pitch:  { applies: false }     # Kokoro ignores pitch — hide the slider
  volume: { min: 0, max: 100, default: 100, applies: true }
  ttl_seconds: { min: 0, max: 300, default: 30, applies: true }
```

An engine that doesn't map a field marks it `applies: false`; the UI reclaims the
space (aligns with `ui_ux_design` §2.2). This replaces ad-hoc per-model branches in
the Rust engine and the frontend.

### 5.5 Consequences

- **Adding a stack, provider, or model is data-only** in the steady state.
- **Persistence is trivial**: writing `user.yaml` is the only mutation site.
- **Diffing is straightforward**: `git diff` on the config folder shows exactly what changed between runs.
- **Testing is decoupled**: engine and renderer tests take a YAML fixture instead of mocking IPC.

---

## 6. Architecture Decision Records (ADRs)

All significant, long-lived architecture decisions for AlienVox are recorded as ADRs in
the **`docs/adr/`** folder (repo root, i.e. `C:\dev\tts\docs\adr\`). Before proposing or
implementing a large design change, **consult the existing ADRs** in that folder for
prior decisions and constraints, and **record new large design decisions** there as a new
`adr-00N-<slug>.md` following the established format (Status, Date, Context, Decision,
Consequences, Related Decisions). Keep ADRs cross-linked and this list current.

### Related Decisions
- [ADR-001](../../docs/adr/adr-001.md) — Selecting Rust + Tauri as the core tech stack (enables this production model).
- [ADR-002](../../docs/adr/adr-002-tauri-production-build.md) — Detailed Tauri production build architecture documentation.
- [ADR-003](../../docs/adr/adr-003-windows-deployment-and-path-resolution.md) — Windows deployment model (NSIS per-user) and unified path resolution (`.models` search order).
- [ADR-004](../../docs/adr/adr-004-tts-stack-architecture.md) — Multi-stack TTS engine architecture (`TtsEngine` trait, `ActiveStack`, per-stack folders).