# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — AlienVox, base tier (SAPI5 only, no ML).

Freezes to a onedir build (not onefile) — onefile extracts to a temp dir
on every launch, which is unacceptable startup latency for a tray app
that should be instant. onedir is the standard shape for both the
portable zip and the Inno Setup installer (install/windows/exe/).

Must be built from a venv that only has install/requirements-base.txt
installed (see install/windows/portable/build_portable.bat) — NOT the
full dev venv. PyInstaller's static analysis finds every literal import
statement in the source, including lazy/function-scoped ones (e.g.
text_enhancer.py's `from llama_cpp import Llama` inside _get_llm()), and
bundles it if the package happens to be importable in the build
environment. Building from a venv that genuinely doesn't have
torch/kokoro/chatterbox-tts/llama-cpp-python installed is what actually
keeps those out, not `excludes=` below (which is only a second layer of
defense, not the primary mechanism).

Usage (from a base-only venv):
    pyinstaller install/windows/alienvox.spec --distpath install/windows/dist --workpath install/windows/build
"""
import sys
from pathlib import Path

block_cipher = None

# This .spec lives in install/windows/ — the app root is two levels up.
APP_ROOT = Path(SPECPATH).resolve().parent.parent
SRC = APP_ROOT / "src"

datas = [
    (str(APP_ROOT / "stacks.yaml"), "."),
    (str(SRC / "resources"), "resources"),
]

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(APP_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # ML engine modules are loaded via importlib.import_module() with a
        # dynamically-built name (see AppController._load_engine) — static
        # analysis can never discover these, and they're deliberately left
        # out here for the base build (not installed in the build venv
        # anyway; the app already handles a missing ML engine module with a
        # caught exception + warning log, not a crash).
    ],
    excludes=[
        # Defense in depth — see module docstring above for why the build
        # venv itself is what actually keeps these out.
        "torch", "transformers", "safetensors", "accelerate",
        "kokoro", "piper", "chatterbox_tts", "f5_tts", "outetts",
        "llama_cpp", "huggingface_hub",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AlienVox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # tray app — no console window
    icon=str(SRC / "resources" / "icons" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="AlienVox",
)
