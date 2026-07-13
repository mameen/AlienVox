# AlienVox Proof of Concept (PoC)

A lightweight tray-first prototype for speaking selected text on Windows/macOS.

## What is required locally?

This prototype uses:

- Python 3.8+ only for bootstrapping and helper scripting
- Rust + Tauri toolchain with `cargo` for the core native app (install Rust separately via https://rustup.rs/)
- Git
- On Windows: Visual Studio Build Tools with the C++ workload

- The `setup.py` script is a bootstrap helper that can install missing Rust/Cargo, Git, Node, and create a local Python virtual environment.

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

## Design

The project is centered on Rust + Tauri. Python is only used for optional setup and developer tooling.

## Next steps

- Replace the sample capture driver with real selection capture.
- Add one local Windows TTS path.
- Add one open-source ML/AI TTS path.
- Keep Python usage limited to tooling and scripting support.
