# AlienVox — Windows Packaging

Turns the app into something a non-developer can run: no Python, no `pip`, no venv.

Both outputs below are **base tier** — Windows SAPI5/Speech Platform voices, no ML, no torch —
same reasoning as `install/requirements-base.txt` one level up: a frozen build that bundled
torch/transformers/every TTS engine package would be multi-GB before a single model checkpoint is
even downloaded. ML support isn't available in either packaged build right now; running from source
with `install/install_ml.bat` is the only way to get it today (see "ML in a packaged build" below).

| | What you get | Build with |
|---|---|---|
| **Portable** (`portable/`) | A zip — extract anywhere, run `AlienVox.exe`. No installer, no registry entries, no admin rights. | `portable\build_portable.bat` |
| **Installer** (`exe/`) | `AlienVoxSetup-<version>.exe` — Start Menu shortcut, optional desktop icon, proper uninstaller. Installs per-user (no admin required). | `exe\build_exe.bat` |

## Building

```bat
cd python_app

rem Portable zip only:
install\windows\portable\build_portable.bat

rem Installer (also produces the portable build as an intermediate step):
install\windows\exe\build_exe.bat
```

The installer build additionally requires the **Inno Setup Compiler** (`ISCC.exe`) — free, from
[jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php). Not installed automatically; the
script checks common install locations and PATH, and tells you clearly if it can't find it.

## Where everything transient lives

Both scripts put **all** transient state — the build venv, PyInstaller's dist/work folders, the
portable zip, and the compiled installer exe — under a single folder:

```
python_app/install/.venv-base-build/
├── Scripts/ Lib/ ...          <- the venv itself (shared by both build scripts)
└── build/
    ├── portable/
    │   ├── dist/AlienVox/     <- PyInstaller onedir output
    │   ├── work/              <- PyInstaller's intermediate build artifacts
    │   └── AlienVox-portable-win64.zip
    └── exe/
        ├── dist/AlienVox/     <- separate freeze, same content, kept independent so
        │                         building one target never clobbers the other's output
        ├── work/
        └── AlienVoxSetup-<version>.exe
```

One `.gitignore` rule (`.venv-base-build/`, matches at any depth) covers the entire tree — nothing
under it can ever be accidentally committed. The venv is shared between `build_portable.bat` and
`build_exe.bat` (created once, reused); each script freezes into its own `build/portable/` or
`build/exe/` subfolder so they don't step on each other if you run both.

The build venv is kept **separate from your dev `.venv`** on purpose: PyInstaller's static analysis
discovers every `import` statement in the source, including lazy/function-scoped ones (e.g.
`text_enhancer.py`'s `from llama_cpp import Llama` inside `_get_llm()`), and bundles whatever's
importable in the build environment. Building from a venv that genuinely doesn't have
torch/kokoro/chatterbox-tts/llama-cpp-python installed is what actually keeps a base build small —
the `excludes=` list in `alienvox.spec` is only a second line of defense, not the primary mechanism.

Verified sizes from an actual build: **~120MB unpacked, ~50MB zipped.**

## Where things end up at runtime

Both packaged builds use the exact same path-resolution logic as running from source
(`src/config.py`):

- `stacks.yaml` / `user.yaml` — next to the installed app (or the extracted portable folder).
- Model weights (`.models/`) — always `%LOCALAPPDATA%\com.alientech.alienvox\.models`, created on
  first use. A frozen build's own install directory isn't a reliable place for multi-GB downloads
  (a portable install in particular might be sitting on read-only or removable media) — see the
  `models_root()` docstring for the frozen-vs-dev resolution rules.
- Telemetry / logs — `%LOCALAPPDATA%\com.alientech.alienvox\telemetry\` and `...\logs\`.

Uninstalling via the installer removes the app folder but deliberately leaves
`%LOCALAPPDATA%\com.alientech.alienvox\.models` alone — a reinstall doesn't force re-downloading
model weights.

## ML in a packaged build

Not available yet in either the portable zip or the installer — both are base-tier only (see the
table above for why). The only way to get ML voices today is running from source and adding
`install\install_ml.bat` on top. An ML-enabled packaged build is possible (freeze from a venv that
has `install/requirements-ml.txt` installed instead of `requirements-base.txt`) but would be a
multi-GB download — a separate, explicitly-opt-in build target if it's ever wanted, not the default.

---

AlienVox is a product of [AlienTech.Software](https://alientech.software/), © 2026. Licensed under
the MIT License — see [LICENSE](../../../LICENSE) in the repository root.
