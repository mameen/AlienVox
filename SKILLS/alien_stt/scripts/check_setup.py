#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that everything alien_stt needs is installed, and say what is missing.

Run it first on a new machine, and whenever a transcription fails before it
starts. It changes nothing and downloads nothing.

Usage
-----
    python scripts/check_setup.py [--model large-v3] [--json]

Checks
------
* Python version
* ffmpeg and ffprobe (required: every format goes through them)
* numpy, soundfile, torch, transformers (required for transcription)
* CUDA GPU (optional: without it work runs on the CPU, much slower for large models)
* whether the chosen model is already in the Hugging Face cache (informational:
  if not, the first run downloads it, which needs network access and disk space)

Exit codes: 0 ready; 1 something required is missing.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import pathlib
import subprocess
import sys

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))

from alienstt import audio as audio_mod                                  # noqa: E402
from alienstt.cli import setup_console                                   # noqa: E402
from alienstt.engines import DEFAULT_MODEL, resolve_model                # noqa: E402


def hf_cache_dir() -> pathlib.Path:
    """Hugging Face hub cache folder, honouring the standard environment variables."""
    if os.environ.get("HF_HUB_CACHE"):
        return pathlib.Path(os.environ["HF_HUB_CACHE"])
    home = pathlib.Path(os.environ.get("HF_HOME") or pathlib.Path.home() / ".cache" / "huggingface")
    return home / "hub"


def model_cached(model_id: str) -> bool:
    """True if a snapshot of `model_id` exists in the local cache (or `model_id` is a local folder)."""
    if pathlib.Path(model_id).is_dir():
        return True
    snap = hf_cache_dir() / ("models--" + model_id.replace("/", "--")) / "snapshots"
    return snap.is_dir() and any(snap.iterdir())


def main(argv=None) -> int:
    setup_console()
    p = argparse.ArgumentParser(description="Check alien_stt prerequisites.")
    p.add_argument("--model", default=DEFAULT_MODEL, help="model to check the cache for")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    add("python", sys.version_info >= (3, 10), sys.version.split()[0] + " (3.10+ needed)")
    for tool in ("ffmpeg", "ffprobe"):
        try:
            path = audio_mod.find_tool(tool)
            first = subprocess.run([path, "-version"], capture_output=True, text=True).stdout.splitlines()[:1]
            add(tool, True, f"{path} ({first[0] if first else 'version unknown'})")
        except audio_mod.ToolNotFoundError as exc:
            add(tool, False, str(exc))
    for mod in ("numpy", "soundfile", "torch", "transformers"):
        try:
            m = importlib.import_module(mod)
            add(mod, True, getattr(m, "__version__", "installed"))
        except Exception as exc:
            add(mod, False, f"{type(exc).__name__}: {exc}; run: pip install -r scripts/requirements.txt")
    try:
        import torch

        gpu = torch.cuda.is_available() and torch.cuda.device_count() > 0
        add("cuda gpu", gpu, torch.cuda.get_device_name(0) if gpu else "none; transcription will use the CPU", required=False)
    except Exception:
        add("cuda gpu", False, "torch unavailable", required=False)
    model_id = resolve_model(args.model)
    cached = model_cached(model_id)
    add("model cache", cached, f"{model_id}: " + ("cached" if cached else f"not cached; first use downloads it (cache: {hf_cache_dir()})"), required=False)

    ready = all(c["ok"] for c in checks if c["required"])
    if args.json:
        print(json.dumps({"ready": ready, "checks": checks}, ensure_ascii=False, indent=2))
    else:
        for c in checks:
            mark = "ok  " if c["ok"] else ("MISS" if c["required"] else "note")
            print(f"[{mark}] {c['name']}: {c['detail']}")
        print("ready" if ready else "NOT ready: fix the MISS lines above")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
