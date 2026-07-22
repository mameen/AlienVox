"""AlienVox environment health check — are we ready to run the app / perf suite?

Checks, in order:
  1. Every runtime package actually imports (not just "pip says installed").
  2. numpy/protobuf land on versions that satisfy every ML engine's pins
     (see requirements.txt comments for why these are capped/floored).
  3. Model weights exist on disk for each entry in stacks.yaml.
  4. Hardware summary (CPU, RAM, GPU/VRAM) — informational, explains why
     perf numbers look the way they do (e.g. CPU-only inference).
  5. Known engine-level limitations, if any, are surfaced as warnings
     rather than silently producing empty audio.

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
    "vibevoice_realtime": "vibevoice",
}

# vibevoice isn't installed by requirements-ml.txt's base ML install (or by
# setup.py's default bootstrap, unlike dia) — see that file's comments for
# why: no PyPI release, git-only, pulls a heavy unrelated WebRTC/server
# dependency set. A missing import here is expected/normal (manual opt-in),
# not a failure — warn instead.
_MANUAL_INSTALL_ENGINES = {"vibevoice_realtime"}

# VibeVoice's preset voices are precomputed .pt files fetched separately
# from the HF weight snapshot (see vibevoice_engine.py's docstring) — the
# generic "any file present" weights check below wouldn't catch a partial
# download (e.g. weights present but only 2 of 6 voices).
_VIBEVOICE_EXPECTED_VOICE_FILES = [
    "en-Carter_man.pt", "en-Davis_man.pt", "en-Frank_man.pt",
    "en-Mike_man.pt", "en-Emma_woman.pt", "en-Grace_woman.pt",
]


def _check_import(module_name: str, is_optional: bool = False) -> CheckResult:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "")
        return CheckResult(module_name, True, version)
    except Exception as exc:
        if is_optional:
            return CheckResult(
                module_name, True,
                f"not installed (manual/opt-in — {type(exc).__name__}: {exc})",
                is_warning=True,
            )
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


def _check_vibevoice_preset_voices(models_root: Path) -> list[CheckResult]:
    """VibeVoice's 6 preset voices are precomputed .pt files fetched
    separately from the HF weight snapshot (via ensure_voice_downloaded()
    or install_dialog.py's Download button) — verify all 6 are actually
    present, not just that the weights directory has *some* content."""
    voices_dir = models_root / "ml" / "vibevoice_realtime" / "voices"
    if not voices_dir.exists():
        return [CheckResult(
            "voices/vibevoice_realtime", True,
            "not downloaded yet — fetched automatically on first use, or via "
            "Settings ▸ vibevoice_realtime ▸ Download",
            is_warning=True,
        )]
    missing = [f for f in _VIBEVOICE_EXPECTED_VOICE_FILES if not (voices_dir / f).exists()]
    if missing:
        return [CheckResult(
            "voices/vibevoice_realtime", True,
            f"{len(_VIBEVOICE_EXPECTED_VOICE_FILES) - len(missing)}/{len(_VIBEVOICE_EXPECTED_VOICE_FILES)} "
            f"present — missing: {', '.join(missing)}",
            is_warning=True,
        )]
    return [CheckResult(
        "voices/vibevoice_realtime", True,
        f"all {len(_VIBEVOICE_EXPECTED_VOICE_FILES)} preset voices present",
    )]


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

    # GPU / VRAM — CUDA devices actually visible to torch right now ...
    cuda_names: set[str] = set()
    cuda_hidden_by_policy = False  # True if torch sees zero devices but a CUDA_VISIBLE_DEVICES override is set
    try:
        import os as _os

        import torch
        # torch.cuda.is_available() can return True with zero visible devices
        # (e.g. CUDA_VISIBLE_DEVICES="" still reports the driver as usable) —
        # device_count() is the real signal for "is there a GPU to use."
        device_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        if device_count > 0:
            for i in range(device_count):
                props = torch.cuda.get_device_properties(i)
                cuda_names.add(props.name)
                results.append(CheckResult(
                    f"GPU {i}", True,
                    f"{props.name} — {props.total_memory / (1024**3):.1f} GB VRAM (CUDA, usable for inference)",
                ))
        else:
            cvd = _os.environ.get("CUDA_VISIBLE_DEVICES")
            cuda_hidden_by_policy = cvd is not None
            detail = (
                f"No CUDA GPU visible — hidden by CUDA_VISIBLE_DEVICES={cvd!r} "
                "(run.py defaults to CPU-only; pass --gpu/--cuda to use a real GPU)"
                if cuda_hidden_by_policy else
                "No CUDA GPU visible to torch — ML engines will run on CPU"
            )
            results.append(CheckResult("GPU (CUDA)", True, detail, is_warning=True))
    except Exception as exc:
        results.append(CheckResult("GPU (CUDA)", True, f"could not query CUDA: {exc}", is_warning=True))

    # ... plus every display adapter Windows knows about (e.g. an AMD iGPU),
    # for visibility even though only CUDA devices above are usable for inference.
    if _platform.system() == "Windows":
        try:
            import subprocess
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=10,
            )
            all_gpus = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            other_gpus = [g for g in all_gpus if g not in cuda_names]
            for g in other_gpus:
                # An NVIDIA card in this list (but not in cuda_names) means it's
                # CUDA-capable but currently hidden by policy, not incapable.
                is_nvidia = "nvidia" in g.lower()
                if is_nvidia and cuda_hidden_by_policy:
                    detail = f"{g} — CUDA-capable, hidden by CPU-only mode (use --gpu to enable)"
                elif is_nvidia:
                    detail = f"{g} — CUDA-capable but not currently visible to torch"
                else:
                    detail = f"{g} — detected, not CUDA-capable"
                results.append(CheckResult("GPU (other)", True, detail))
        except Exception:
            pass  # best-effort — WMI/PowerShell may be unavailable

    return results


# ── Known engine limitations ──────────────────────────────────────────────────
# Currently empty — kept as an extension point for surfacing engine-level
# limitations (like Piper's now-fixed synthesize() stub) as warnings instead
# of letting them silently produce empty/failed audio.

def _check_known_limitations() -> list[CheckResult]:
    return []


def hardware_summary_lines() -> list[str]:
    """CPU/RAM/GPU one-liners for a quick startup banner.

    Reuses the same detection as `python run.py health` but skips the WMI
    "other display adapters" query (a few seconds via PowerShell) — too
    slow to run on every app startup, and not needed for a one-line summary.
    """
    lines = []
    for r in _check_hardware():
        if r.label.startswith("GPU (other)"):
            continue
        lines.append(f"{r.label}: {r.detail}")
    return lines


def list_running_instances() -> list[dict]:
    """Find other AlienVox app processes (python running src.main), for
    `python run.py health` to surface PIDs the user can shut down.

    Best-effort: requires psutil, and only sees processes visible to the
    current user (which is the common case on a single-user Windows box).
    """
    try:
        import psutil  # type: ignore
    except ImportError:
        return []

    instances = []
    current_pid = None
    import os
    current_pid = os.getpid()

    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            joined = " ".join(cmdline)
            if "src.main" not in joined and "src\\main.py" not in joined and "src/main.py" not in joined:
                continue
            if proc.info["pid"] == current_pid:
                continue
            instances.append({
                "pid": proc.info["pid"],
                "cmdline": joined,
                "create_time": proc.info.get("create_time"),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return instances


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
    import_results += [
        _check_import(module_name, is_optional=(engine_id in _MANUAL_INSTALL_ENGINES))
        for engine_id, module_name in _ML_ENGINE_IMPORTS.items()
    ]
    _print_section("Package imports", import_results)

    version_results = [_check_numpy_version(), _check_protobuf_version()]
    _print_section("Version pins", version_results)

    from .config import models_root as _models_root
    stacks_yaml = ROOT / "stacks.yaml"
    mr = _models_root()
    weight_results = _check_model_weights(stacks_yaml, mr)
    weight_results += _check_vibevoice_preset_voices(mr)
    _print_section("Model weights (.models/)", weight_results)

    hardware_results = _check_hardware()
    _print_section("Hardware", hardware_results)

    running = list_running_instances()
    print("\nRunning AlienVox instances")
    print("-" * len("Running AlienVox instances"))
    if running:
        for inst in running:
            print(f"  PID {inst['pid']:<8} {inst['cmdline']}")
        print("  (only one instance is allowed to run at a time — "
              "close these before starting a new one, e.g. "
              "`taskkill /PID <pid> /F` on Windows)")
    else:
        print("  (none)")

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
