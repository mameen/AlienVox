# AlienVox — Install

Running from source, for developers (or anyone with Python already installed) — see below. If you
just want a runnable app with no Python install at all, see **[windows/](windows/README.md)** for
the portable zip and the Windows installer.

## From source: two layers, both optional after the first

| Layer | What it gets you | Size | Script | Installs from |
|---|---|---|---|---|
| **Base** | Tray + main window, Windows SAPI5/Speech Platform voices | ~150–300MB (PySide6, pywin32, ...) | `install.bat` | `install/requirements-base.txt` |
| **ML** | Local open-source voices (Kokoro, Chatterbox, Piper, F5-TTS, OuteTTS) + LLM text enhancement | multi-GB (torch, transformers, TTS engine packages) | `install_ml.bat` | the root `requirements.txt` (same file `python setup.py` uses) |

`install/requirements-base.txt` stays a separate, genuinely base-only file on purpose — it's not
just a lighter option for `install.bat`, it's a hard requirement for the Windows packaged builds
(see `windows/README.md`): PyInstaller bundles whatever's importable in the venv it's frozen from,
so keeping that venv free of torch/ML packages is the actual mechanism that keeps the shipped
`.exe`/portable zip small. There used to be a matching `install/requirements-ml.txt` too, but
nothing else depended on it being separate from the root `requirements.txt` — it was pure
duplication (and had already drifted out of sync), so `install_ml.bat` now installs the root file
directly instead.

Model **weights** (the actual checkpoints — Kokoro ~300MB, Chatterbox ~1-2GB, Dia ~3GB+, the
Qwen enhancer ~470MB, ...) are never part of either install step. They download **lazily, one
model at a time**, the first time you select that model or click "Install Model" in the app
(or via `python run.py download`). That's the piece that would genuinely hit multiple GB if
bundled up front — so it isn't.

## Quick start

```bat
cd python_app
install\install.bat
python run.py app
```

That's the whole base install — you're speaking with Windows' built-in SAPI5 voices immediately,
no large downloads.

## Adding ML voices later

```bat
install\install_ml.bat
```

Then pick a model in the app's ML/AI tab and click "Install Model" (or preview it directly —
installing happens the first time it's actually used). Each model's weights download once and
are cached under `.models/`.

## Performance testing extras

`psutil` and `nvidia-ml-py` (used by `tests/test_perf.py` / `python run.py perf` for the
device/CPU/memory/GPU columns) are declared in the root `requirements.txt`, so `install_ml.bat`
(and `python setup.py`) both get them automatically. A base-only install (`install.bat`) won't
have them — `pip install psutil nvidia-ml-py` directly if you want to run `run.py perf` without
the rest of the ML layer.

## Why split it this way

For a first-time user who just wants "highlight text, press a hotkey, hear it," forcing a
multi-GB torch/transformers download before they can even try the app is the wrong default.
Base-first, ML-opt-in mirrors how the app already treats model weights: nothing large happens
until you ask for it. Beyond that UX preference, `install/requirements-base.txt` specifically is
also load-bearing for the Windows packaged-build pipeline (see above) — that's the one file in
this split that isn't just a convenience duplicate.

---

AlienVox is a product of [AlienTech.Software](https://alientech.software/), © 2026. Licensed under
the MIT License — see [LICENSE](../../LICENSE) in the repository root.
