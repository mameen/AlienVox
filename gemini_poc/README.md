# AlienVox Proof of Concept (PoC) Setup Guide

This guide provides the instructions to configure, build, and run the `alienvox_prototype` codebase from inside your designated workspace environment.

## 1. Prerequisites & Environment Setup

Before compiling the Rust and Tauri subsystems, ensure your host environment satisfies the necessary compilation toolchains.

### Windows 11 Requirements
1. **Microsoft Visual Studio C++ Build Tools:** Download the Visual Studio Installer and ensure **Desktop development with C++** is checked.
2. **WebView2 Runtime:** Built-in on Windows 11, but ensure it is updated to the latest stable runtime if using an enterprise long-term servicing branch.

### macOS 14+ Requirements
1. **Xcode Command Line Tools:** Execute the following initialization sequence in your terminal terminal:
   ```bash
   xcode-select --install
   ```

---

## 2. Directory Layout & Dependency Setup

Extract your project archive directly into your targeted active directory structure:

```text
C:\dev	ts\.repos\gemini_poc├── Cargo.toml               # Core Manifest & Conditionals
└── src/
    ├── main.rs              # App Entry Point & System Tray
    ├── audio/
    │   ├── mod.rs           # Audio Pipeline Interface Bridge
    │   ├── audio_win.rs     # Windows Native SAPI Layer
    │   └── audio_mac.rs     # macOS Native AVFoundation Layer
    └── capture/
        ├── mod.rs           # Text Capture Dispatcher Interface
        ├── capture_win.rs   # Windows UI Automation Framework Hooks
        └── capture_mac.rs   # macOS AXUIElement Accessibility Hooks
```

---

## 3. Step-by-Step Compilation and Execution

Follow these precise steps from your terminal execution window to stand up and initialize the workspace target.

### Step 1: Navigate to the Repository Root
```bash
cd C:\dev\tts\.repos\gemini_poc
```

### Step 2: Validate Target Dependencies
Verify your Rust development environment is fully updated and targeted correctly to pull the native platform dependencies (`windows-sys` on Windows or `cocoa`/`objc` on Mac):
```bash
cargo check
```

### Step 3: Run the Application Prototype
Execute the native compilation loop. This compiles the platform-agnostic business logic handlers alongside your explicit OS-suffixed execution streams:
```bash
cargo run
```

---

## 4. Operational Verification

1. **Background Tray Execution:** Once launched, the utility immediately ducks into your OS background context.
   - **Windows:** Look for the application running silently inside your active Taskbar System Tray.
   - **macOS:** Look for the application tracking hook in the upper Status Menu Bar.
2. **Context Subsystem Interactivity:** Right-click the system icon anchor to verify thread controls. Clicking **Mute/Unmute** or interacting with the hotkey interface maps to the underlying zero-latency OS abstract hooks, routing real-time text structures through the native execution pipelines.
3. **Clean Termination:** Select **Quit AlienVox** from the context window to gracefully flush the active threads and completely drop out of the system environment memory space.
