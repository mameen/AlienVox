# Architecture Decision Record (ADR)
## ADR-001: Selection of Tech Stack for AlienVox — Python + PySide6

| Attribute | Specification |
| :--- | :--- |
| **Status** | Accepted |
| **Date** | July 18, 2026 |
| **Author** | Principal Architect |
| **Project Context** | AlienVox — python_app (AlienTech.Software) |

---

## Context and Problem Statement

The `gemini_poc` (Rust + Tauri) proved that the UI layer and the ML inference layer cannot be unified through Rust without substantial complexity: Rust cannot natively import PyTorch checkpoints, so every ML model required a Python subprocess at runtime. This is hidden-backend architecture and violates the standalone app requirement.

We need a stack where:
1. The UI layer and ML inference layer are the **same runtime** — no subprocess boundary.
2. Native Windows APIs (SAPI5 via COM, UI Automation, system tray, global hotkeys) are accessible.
3. Local ML inference runs in-process (PyTorch, ONNX Runtime, Kokoro, Piper, Dia).
4. The result can be frozen into a single-file executable (PyInstaller / Nuitka).

---

## Decision

**Selected: Python 3.11+ with PySide6**

### Why Python
- PyTorch, Kokoro, Piper (ONNX), Dia, and all SOTA TTS libraries are natively Python. Running them in-process eliminates the subprocess boundary.
- `pywin32` / `comtypes` provide full SAPI5 COM access, WinRT access, and UI Automation without a C# bridge.
- `pynput` provides reliable cross-platform global hotkey listening.
- PyInstaller / Nuitka can freeze the app + venv into a standalone `.exe`.

### Why PySide6 (not PyWebView, not Electron, not Tkinter)
- PySide6 is the official Qt6 Python binding — native widgets, native system tray (`QSystemTrayIcon`), native file dialogs, native menus. No browser engine dependency.
- `QSystemTrayIcon` + `QMenu` is the correct primitive for a tray-first app on Windows and macOS.
- Qt6 ships WebEngine if a WebView is ever needed, but the primary surface is native Qt widgets, not HTML.
- Tkinter lacks a native tray; PyWebView embeds a browser runtime (not standalone); Electron requires Node.js.

### Why not Rust + Tauri (gemini_poc)
- Rust cannot import Python ML checkpoints at runtime without a subprocess.
- A subprocess is a hidden backend — it violates the standalone app requirement.
- ~1000 lines of Rust in `engines/ml.rs` doing nothing but launching Python processes provides no value over running Python directly.

---

## Consequences

### Benefits
- **True standalone**: ML inference is in-process; no Python subprocess at runtime.
- **Simpler architecture**: one language, one runtime, one `pip install` for all dependencies.
- **Better ML ecosystem**: full PyTorch, HuggingFace, Kokoro, Piper ONNX, Dia — all native, no adaptation layer.
- **Faster iteration**: change inference code and UI code in the same repo, same language.

### Trade-offs
- **Binary size**: a frozen Python app is ~80–200 MB (Python runtime + torch). Acceptable for a desktop utility.
- **Startup time**: Python startup is slower than native binary. Mitigated by keeping the app resident in the tray (start once, never restart).
- **Memory footprint**: Python base runtime is ~20–40 MB idle, higher than a Rust binary. Still meets the sub-10MB-idle goal only if torch is not imported until needed — lazy ML import is mandatory.

---

## Related Decisions
- ADR-002 (to be written) — Windows deployment and path resolution for python_app.
- ADR-003 (to be written) — Multi-stack TTS engine architecture in Python.
