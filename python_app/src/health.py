"""AlienVox environment health check — are we ready to run the app / perf suite?

Checks, in order:
  1. Every runtime package actually imports (not just "pip says installed").
  2. numpy/protobuf land on versions that satisfy every ML engine's pins
     (see requirements.txt comments for why these are capped/floored).
  3. Model weights exist on disk for each entry in stacks.yaml.
  4. Hardware summary (CPU, RAM, GPU/VRAM) — informational, explains why
     perf numbers look the way they do (e.g. CPU-only inference).
  5. Known engine-level limitations (e.g. Piper's synthesize() stub) are
     surfaced as warnings rather than silently producing empty audio.

Usage:
    python -m src.health          (invoked by `python run.py health`)

Exit code 0 if nothing is FAIL (warnings are still exit 0); 1 otherwise.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent


class CheckResult(NamedTuple):
    label: str
    ok: bool
    detail: str
    is_warning: bool = False


# ── Package imports ─────────────────────────────────────────────────────────

_REQUIRED_IMPORTS = [
    "PySide6", "pynput", "yaml", "sounddevice", "soundfile", "numpy",
    "lameenc", "torch", "transformers", "safetensors", "accelerate",
    "huggingface_hub", "dotenv",
]

_ML_ENGINE_IMPORTS = {
    "kokoro": "kokoro",
    "piper": "piper",
    "chatterbox": "chatterbox",
    "f5tts": "f5_tts",
    "outetts": "outetts",
    "dia": "dia",
}


def _check_import(module_name: str) -> CheckResult:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "")
        return CheckResult(module_name, True, version)
    except Exception as exc:
        return CheckResult(module_name, False, f"{type(exc).__name__}: {exc}")


# ── Version pins ─────────────────────────────────────────────────────────────

def _check_numpy_version() -> CheckResult:
    try:
        import numpy
        v = tuple(int(p) for p in numpy.__version__.split(".")[:2])
        ok = v < (2, 0)
        return CheckResult(
            "numpy version", ok,
            f"{numpy.__version__} (<2.0.0 required — chatterbox-tts pin)",
        )
    except Exception as exc:
        return CheckResult("numpy version", False, str(exc))


def _check_protobuf_version() -> CheckResult:
    try:
        import google.protobuf
        v = tuple(int(p) for p in google.protobuf.__version__.split(".")[:2])
        ok = v >= (4, 25)
        return CheckResult(
            "protobuf version", ok,
            f"{google.protobuf.__version__} (>=4.25.8 required — onnx/onnxruntime pin)",
        )
    except Exception as exc:
        return CheckResult("protobuf version", False, str(exc))


# ── Model weights ────────────────────────────────────────────────────────────

def _check_model_weights(stacks_yaml: Path, models_root: Path) -> list[CheckResult]:
    import yaml
    results: list[CheckResult] = []
    if not stacks_yaml.exists():
        return [CheckResult("stacks.yaml", False, f"not found at {stacks_yaml}")]

    with open(stacks_yaml, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    for stack in catalog.get("stacks", []):
        if stack["id"] != "ml":
            continue
        for model in stack.get("models", []):
            mid = model["id"]
            wsub = model.get("weights_subpath", "")
            auto_dl = model.get("auto_download", False)
            if not wsub:
                continue
            path = models_root / wsub
            has_content = path.exists() and any(path.rglob("*"))
            if has_content:
                n_files = sum(1 for _ in path.rglob("*") if _.is_file())
                results.append(CheckResult(f"weights/{mid}", True, f"{n_files} file(s) in {wsub}"))
            elif auto_dl:
                results.append(CheckResult(
                    f"weights/{mid}", True,
                    "not on disk yet — auto_download will fetch on first speak()",
                    is_warning=True,
                ))
            else:
                results.append(CheckResult(
                    f"weights/{mid}", False,
                    f"missing at .models/{wsub} — run `python run.py download`",
                ))
    return results


# ── Hardware ─────────────────────────────────────────────────────────────────
# Informational only — doesn't affect READY/NOT READY, but perf numbers are
# meaningless without knowing what they were measured on.

def _check_hardware() -> list[CheckResult]:
    import os
    import platform as _platform
    results: list[CheckResult] = []

    cpu_name = _platform.processor() or _platform.uname().processor or "unknown"

    # CPU
    try:
        import psutil  # type: ignore
        physical = psutil.cpu_count(logical=False) or 0
        logical = psutil.cpu_count(logical=True) or 0
        results.append(CheckResult(
            "CPU", True, f"{cpu_name} — {physical} physical / {logical} logical cores",
        ))
    except ImportError:
        results.append(CheckResult(
            "CPU", True,
            f"{cpu_name} — {os.cpu_count() or 0} logical cores (psutil not installed for physical count)",
        ))

    # RAM
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        results.append(CheckResult(
            "RAM", True,
            f"{vm.total / (1024**3):.1f} GB total, {vm.available / (1024**3):.1f} GB available",
        ))
    except ImportError:
        results.append(CheckResult("RAM", True, "psutil not installed — install it for RAM info", is_warning=True))

    # GPU / VRAM
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                results.append(CheckResult(
                    f"GPU {i}", True,
                    f"{props.name} — {props.total_memory / (1024**3):.1f} GB VRAM (CUDA)",
                ))
        else:
            results.append(CheckResult(
                "GPU", True, "No CUDA GPU detected — ML engines will run on CPU",
                is_warning=True,
            ))
    except Exception as exc:
        results.append(CheckResult("GPU", True, f"could not query GPU: {exc}", is_warning=True))

    return results


# ── Known engine limitations ──────────────────────────────────────────────────

def _check_known_limitations() -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        from .engines.piper_win import PiperEngine
        import inspect
        src = inspect.getsource(PiperEngine._synthesize)
        if 'return b""' in src or "Placeholder" in src:
            results.append(CheckResult(
                "piper synthesis", True,
                "PiperEngine._synthesize() is still a stub — Piper will produce "
                "silent/failed output even with weights present",
                is_warning=True,
            ))
    except Exception:
        pass  # best-effort — don't fail health check over this probe
    return results


# ── Report rendering ──────────────────────────────────────────────────────────

def _print_section(title: str, results: list[CheckResult]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for r in results:
        if r.ok and not r.is_warning:
            tag = "OK  "
        elif r.is_warning:
            tag = "WARN"
        else:
            tag = "FAIL"
        print(f"  [{tag}] {r.label:<24} {r.detail}")


def run() -> int:
    # Windows consoles often default to cp1252, which can't encode the
    # em dashes used in this module's messages — force UTF-8 output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("AlienVox Health Check")
    print(f"Python: {sys.version.splitlines()[0]}")

    import_results = [_check_import(m) for m in _REQUIRED_IMPORTS]
    import_results += [_check_import(m) for m in _ML_ENGINE_IMPORTS.values()]
    _print_section("Package imports", import_results)

    version_results = [_check_numpy_version(), _check_protobuf_version()]
    _print_section("Version pins", version_results)

    from .config import models_root as _models_root
    stacks_yaml = ROOT / "stacks.yaml"
    weight_results = _check_model_weights(stacks_yaml, _models_root())
    _print_section("Model weights (.models/)", weight_results)

    hardware_results = _check_hardware()
    _print_section("Hardware", hardware_results)

    limitation_results = _check_known_limitations()
    if limitation_results:
        _print_section("Known limitations", limitation_results)

    all_results = import_results + version_results + weight_results + hardware_results + limitation_results
    failures = [r for r in all_results if not r.ok and not r.is_warning]
    warnings = [r for r in all_results if r.is_warning]

    print()
    if failures:
        print(f"NOT READY — {len(failures)} failure(s), {len(warnings)} warning(s).")
        return 1

    status = "READY" if not warnings else f"READY (with {len(warnings)} warning(s))"
    print(status + ".")
    return 0


if __name__ == "__main__":
    sys.exit(run())
