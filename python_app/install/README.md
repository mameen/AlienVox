# AlienVox — Install

Running from source, for developers (or anyone with Python already installed) — see below. If you
just want a runnable app with no Python install at all, see **[windows/](windows/README.md)** for
the portable zip and the Windows installer.

## From source: two layers, both optional after the first

| Layer | What it gets you | Size | Script |
|---|---|---|---|
| **Base** | Tray + main window, Windows SAPI5/Speech Platform voices | ~150–300MB (PySide6, pywin32, ...) | `install.bat` |
| **ML** | Local open-source voices (Kokoro, Chatterbox, Piper, F5-TTS, OuteTTS) + LLM text enhancement | multi-GB (torch, transformers, TTS engine packages) | `install_ml.bat` |

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

## What's deliberately left out

`psutil` (used only by `tests/test_perf.py`'s memory/CPU benchmarks) isn't in either file — it's a
dev-only dependency, not something a regular install needs. `pip install psutil` if you're running
`python run.py perf` outside of the full dev `requirements.txt`.

## Why split it this way

The repo's top-level `requirements.txt` still installs everything in one shot (kept for CI/dev,
where the full ML stack is exercised by the test suite anyway). For a first-time user who just
wants "highlight text, press a hotkey, hear it," forcing a multi-GB torch/transformers download
before they can even try the app is the wrong default. Base-first, ML-opt-in mirrors how the app
already treats model weights: nothing large happens until you ask for it.

---

AlienVox is a product of [AlienTech.Software](https://alientech.software/), © 2026. Licensed under
the MIT License — see [LICENSE](../../LICENSE) in the repository root.
