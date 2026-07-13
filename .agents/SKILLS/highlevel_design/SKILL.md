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

## 4. Related Decisions
- [ADR-001](../../docs/adr/adr-001.md) — Selecting Rust + Tauri as the core tech stack (enables this production model).
- [ADR-002](../../docs/adr/adr-002-tauri-production-build.md) — Detailed Tauri production build architecture documentation.