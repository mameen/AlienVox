# AlienVox Proof of Concept (PoC)

A lightweight tray-first prototype for speaking selected text on Windows/macOS.

This prototype is built on Rust + Tauri as the core application architecture. Python is used only for optional bootstrapping and scripting support.

## Requirements

- Python 3.8+ for setup scripting
- Rust toolchain with `cargo` (install Rust separately via https://rustup.rs/)
- Git
- On Windows: Visual Studio Build Tools with the C++ workload

## Bootstrap the workspace

From the `gemini_poc/` folder:

```bat
cd C:\dev\tts\gemini_poc
python setup.py
```

## Build and run

```bat
cargo run
```

## Notes

- The `setup.py` helper verifies local tools and creates a Python virtual environment.
- The core application remains Rust + Tauri.
- Python is limited to tooling and scripting support, not the runtime.

## Next steps

- Replace the sample capture driver with real selection capture.
- Add one local Windows TTS path.
- Add one open-source ML/AI TTS path.
- Keep Python usage limited to scripting and tooling support.
