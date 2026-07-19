# AlienTech.Software Engineering Standards
## Cross-Platform Development & Implementation Guidelines

| Attribute | Specification |
| :--- | :--- |
| **Document ID** | ENG-STD-004 |
| **Author** | Principal Architect |
| **Project Context** | AlienVox (Read-Selection Utility) |
| **Target Audience** | Core App Engineers |
| **Status** | Approved |

---

## 1. Architectural Strategy: The Bridge Pattern
To prevent platform-specific code from polluting core business logic, AlienTech projects mandate a strict separation of concerns using a **Bridge/Interface Pattern**. 

1. **The Core (Platform-Agnostic):** Houses state management, configurations, UI layout, and orchestrations. It must never import OS-specific APIs.
2. **The Interface (Contract):** Defines abstract protocols, interfaces, or headers describing *what* must happen (e.g., `capture_selection()`).
3. **The Implementations (Platform-Specific):** Concrete, isolated files or folders containing OS-native calls.

---

## 2. Code Organization & File Naming Conventions

We utilize a hybrid approach combining **Suffix Naming** for smaller standalone modules and **Directory Separation** for heavy subsystems.

### 2.1 File Suffix Naming Strategy
For lightweight platform variances (e.g., global hotkeys, notification triggers), use explicit file suffixes.

* `*._core.*` / `*._base.*` — Platform-agnostic interface/protocol definition.
* `*_win.*` — Windows-specific code (Win32, COM, UI Automation, pywin32).
* `*_mac.*` — macOS-specific code (AppKit, Cocoa, AVFoundation, PyObjC).
* `*_lnx.*` — Linux-specific code (X11, Wayland, DBus).

**Example Directory Map (Python context for AlienVox):**
```text
src/
├── main.py                  # Agnostic Entry Point
├── config.py                # Agnostic State Management
├── engines/
│   ├── base.py              # Abstract TtsEngine protocol
│   ├── sapi_win.py          # SAPI5 / Windows implementation
│   ├── avfoundation_mac.py  # AVFoundation implementation
│   └── espeak_lnx.py        # eSpeak implementation
```

### 2.2 Directory-Based Isolation Strategy
For heavy subsystems (e.g., deep Accessibility API mapping or low-level capture hooks), separate platform logic into dedicated folders under a unified dispatcher interface.

```text
src/
└── capture/
    ├── __init__.py          # Unified entry dispatcher (imports platform impl)
    ├── base.py              # Common type definitions & abstract interface
    ├── win/
    │   ├── automation.py    # Windows UI Automation structures
    │   └── clipboard.py     # Win32 Clipboard API hooks
    └── mac/
        ├── accessibility.py # AXUIElement integrations
        └── clipboard.py     # NSPasteboard integrations
```

---

## 3. Conditional Dispatch & Dependency Isolation

Platform-specific modules must never break import pipelines when loaded on an alternate OS. Guard platform imports at the top of each platform-specific file and in the dispatcher.

### 3.1 Python dispatcher pattern

```python
# src/capture/__init__.py
import sys

if sys.platform == "win32":
    from .win.automation import WindowsCapture as _Impl
elif sys.platform == "darwin":
    from .mac.accessibility import MacCapture as _Impl
else:
    raise ImportError(f"Platform {sys.platform!r} is not yet supported")

capture = _Impl()
```

Each platform file guards its OS imports at the top:

```python
# src/capture/win/automation.py
import sys
if sys.platform != "win32":
    raise ImportError("win/automation is Windows-only")

import win32com.client  # only imported on Windows
```

### 3.2 Conditional dependencies in requirements

Annotate platform-scoped packages with the `; sys_platform` marker:

```
pywin32>=306; sys_platform == "win32"
PyObjC>=10.0; sys_platform == "darwin"
```

---

## 4. The 4 Golden Rules of Cross-Platform Clean Code

1. **No "Leakage":** If a function signature requires a Win32 `HWND` or an Apple `NSView`, it belongs entirely inside a `_win` or `_mac` file. Pass primitives or common types (`str`, `list`, `dict`) back to the Core.
2. **Graceful Fallbacks:** If an OS feature is unimplemented on a platform, the implementation file must raise `ImportError` or `NotImplementedError` at import time — not silently at runtime.
3. **Agnostic Error Handling:** Map OS-specific errors (e.g., `HRESULT` on Windows, `OSStatus` on macOS) into a unified application-level exception class defined in the base interface file.
4. **Cross-Platform Tests:** Every platform-specific module must have tests that skip (not fail) when run on a non-matching OS. CI matrix must cover `windows-latest` and `macos-latest`.
