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
2. **The Interface (Contract):** Defines abstract traits, interfaces, or headers describing *what* must happen (e.g., `capture_selection()`).
3. **The Implementations (Platform-Specific):** Concrete, isolated files or folders containing OS-native calls.

---

## 2. Code Organization & File Naming Conventions

We utilize a hybrid approach combining **Suffix Naming** for smaller standalone modules and **Directory Separation** for heavy subsystems.

### 2.1 File Suffix Naming Strategy
For lightweight platform variances (e.g., global hotkeys, notification triggers), use explicit file suffixes.

* `*._core.*` / `*._base.*` — Platform-agnostic interface/trait definition.
* `*_win.*` — Windows-specific code (Win32, COM, UI Automation).
* `*_mac.*` — macOS-specific code (AppKit, Cocoa, AVFoundation).
* `*_lnx.*` — Linux-specific code (X11, Wayland, DBus).

**Example Directory Map (Rust / Tauri context for AlienVox):**
```text
src/
├── main.rs                  # Agnostic Entry Point
├── config.rs                # Agnostic State Management
├── audio/
│   ├── mod.rs               # Interface definition (Trait AudioEngine)
│   ├── audio_win.rs         # SAPI5 / Windows Media implementation
│   ├── audio_mac.rs         # AVFoundation implementation
│   └── audio_lnx.rs         # PulseAudio / ALSA implementation
```

### 2.2 Directory-Based Isolation Strategy
For heavy subsystems (e.g., deep Accessibility API mapping or low-level OCR hooks), separate platform logic into dedicated folders under a unified dispatcher interface.

```text
services/text_capture/
├── mod.rs                   # Unified entry dispatcher
├── interface.rs             # Common Type definitions & Traits
├── win/
│   ├── automation.rs        # Heavy Windows UI Automation structures
│   └── clipboard.rs         # Win32 Clipboard API hooks
├── mac/
│   ├── accessibility.rs     # AXUIElement integrations
│   └── clipboard.rs         # NSPasteboard integrations
```

---

## 3. Conditional Compilation & Dependency Isolation

Platform-specific files must never break compilation pipelines when built on an alternate OS. Use compiler directives strictly at the top of files and inside dependency manifests.

### 3.1 Rust (`Cargo.toml` & Attributes)
Do not include Windows dependencies globally if they fail to compile on Mac.

```toml
# Cargo.toml - Conditional Dependencies
[target.'cfg(target_os = "windows")'.dependencies]
windows-sys = { version = "0.52", features = ["Win32_UI_Accessibility", "Win32_System_DataExchange"] }

[target.'cfg(target_os = "macos")'.dependencies]
cocoa = "0.25"
objc = "0.2"
```

In your module routing file (`mod.rs`), conditionally compile your suffix files:

```rust
// services/text_capture/mod.rs

// 1. Core shared interface
pub trait TextCapturer {
    fn capture_selection(&self) -> Result<String, CaptureError>;
}

// 2. Conditional module binding
#[cfg(target_os = "windows")]
#[path = "audio_win.rs"]
mod os_impl;

#[cfg(target_os = "macos")]
#[path = "audio_mac.rs"]
mod os_impl;

// 3. Re-export the active implementation as a unified type
pub use os_impl::NativeAudioEngine;
```

### 3.2 C++ / C# Preprocessor Directives
When implementing native extensions or utilizing C#/.NET multi-targeting:

```csharp
// ClipboardService.cs
public class ClipboardService 
{
    public string GetTextData() 
    {
        #if WINDOWS
            return WindowsClipboard.ReadText();
        #elif MACCATALYST || MACOS
            return MacPasteboard.ReadText();
        #else
            throw new PlatformNotSupportedException();
        #endif
    }
}
```

---

## 4. The 4 Golden Rules of Cross-Platform Clean Code

1. **No "Leakage":** If a function signature requires a Win32 `HWND` or an Apple `NSView`, it belongs entirely inside a `_win` or `_mac` file. Pass raw pointers, primitives, or common types (`String`, `Vector`) back to the Core.
2. **Graceful Fallbacks:** If an OS feature is unimplemented on Linux, the implementation file must gracefully compile and return a structured error (`Result::Err(PlatformFeatureUnsupported)`), rather than causing an absolute crash.
3. **Agnostic Error Handling:** Map OS-specific system errors (e.g., `HRESULT` errors on Windows) into a unified application-level enum structure defined in the base interface file.
4. **Automated Cross-Compiling Tests:** Every platform-specific file must possess unit tests encapsulated inside its own module block. Ensure CI/CD configurations pass matrix checks across `ubuntu-latest`, `windows-latest`, and `macos-latest`.
