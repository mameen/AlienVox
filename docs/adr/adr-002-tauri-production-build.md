# Architecture Decision Record (ADR)
## ADR-002: Tauri Production Build Architecture — Single Standalone Binary

| Attribute | Specification |
| :--- | :--- |
| **Status** | Accepted |
| **Date** | July 13, 2026 |
| **Author** | Principal Architect |
| **Project Context** | AlienVox (AlienTech.Software) |

---

## Context and Problem Statement

Developers unfamiliar with Tauri's architecture may incorrectly assume that AlienVox depends on an external Node.js or HTTP server at runtime. The `cargo tauri dev` command starts a local development server for hot-reloading UI code, which creates confusion about the production deployment model. This record explicitly clarifies how Tauri produces a **single, standalone binary** with zero runtime server dependencies.

---

## Decision

Tauri's production build pipeline (`cargo tauri build`) ensures AlienVox ships as a single, self-contained executable by:

### 1. Inlining the Frontend
During the production build phase:
- The frontend (HTML, CSS, TypeScript/JavaScript) is compiled, bundled, and minified.
- Tauri embeds these assets directly into the compiled Rust binary using Rust's `include_bytes!` macro mechanism.
- The frontend exists as raw byte assets inside the binary — not as separate files on disk.

### 2. Zero-Network IPC (Inter-Process Communication)
Because the frontend is embedded:
- No HTTP server runs at runtime. The `localhost:3000` dev server does **not** exist in production.
- Tauri boots the OS's native webview container:
  - **WebView2** (Microsoft Edge Chromium) on Windows
  - **WebKit** on macOS
- The embedded HTML loads directly from memory into the webview process.
- Communication between the UI layer and Rust backend uses Tauri's native OS-level IPC bridge — not HTTP endpoints.

### Development vs. Production Summary

| Phase | What Happens Behind the Scenes | Is There a Server? |
| :--- | :--- | :--- |
| **Development**<br>`cargo tauri dev` | A temporary, local-only tooling process hosts TypeScript/HTML files so UI changes mirror instantly without forcing a full Rust re-compilation. | **Temporarily — yes**<br>Local host process strictly for the developer's machine only. |
| **Production**<br>`cargo tauri build` | TypeScript and HTML files are baked directly into the `.exe` (Windows) or `.app` (macOS) binary alongside Rust code. | **No**<br>Completely self-contained, standalone desktop binary. Zero server dependencies. |

---

## Consequences

### Benefits
- **Deployment Simplicity**: Single executable per platform — no installers, no runtime prerequisites (other than OS webview components which ship with all modern Windows 11 / macOS 14+ systems).
- **No Runtime Server Overhead**: Zero memory or CPU cost for a dev server process. All resources contribute to the sub-10MB idle footprint goal.
- **Security**: No HTTP listeners mean no risk of network-based attacks targeting a local development server.
- **Predictable Behavior**: The app behaves identically in development and production — frontend always loads from binary, never from a network port.

### Trade-offs
- **Longer Iteration Time During Development**: UI changes require full `cargo tauri build` cycles if not using `cargo tauri dev`. Developers must use the dev server for productive UI iteration.
- **Binary Size**: Embedded frontend assets increase binary size slightly (typically 2–5 MB depending on UI complexity).

---

## Related Decisions
- [ADR-001](./adr-001.md) — Selecting Rust + Tauri as the core tech stack (enables this production model).