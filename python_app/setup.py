"""AlienVox python_app bootstrap — creates venv, installs requirements, and downloads ML models."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"


def _ensure_bootstrap_deps() -> None:
    """Install setup.py's own dependencies (pyyaml, python-dotenv) if missing.

    setup.py's job is to install requirements.txt into a venv — but it needs
    yaml/dotenv itself just to run. Bootstrap them into whatever interpreter
    is currently running this script, so `python setup.py` works cold with
    no manual `pip install` beforehand.
    """
    missing = []
    try:
        import yaml  # noqa: F401
    except ImportError:
        missing.append("pyyaml")
    try:
        import dotenv  # noqa: F401
    except ImportError:
        missing.append("python-dotenv")

    if missing:
        print(f"Bootstrapping setup.py dependencies: {', '.join(missing)}...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *missing], check=True)


_ensure_bootstrap_deps()

from dotenv import load_dotenv  # noqa: E402
import yaml  # noqa: E402

# Load .env so HF_TOKEN is available for gated repos
_load_dotenv = load_dotenv(ROOT / ".env", override=False)

# HuggingFace repos (must match install_dialog.py and engine source files)
_KOKORO_HF_REPO = "hexgrad/Kokoro-82M"
_PIPER_HF_REPO = "rhasspy/piper-voices"
_CHATTERBOX_HF_REPO = "ResembleAI/chatterbox"
_DIA_HF_REPO = "nari-labs/Dia-1.6B-0626"  # dia package (git HEAD) requires the new config schema
_F5TTS_HF_REPO = "SWivid/F5-TTS"
_OUTETTS_HF_REPO = "OuteAI/OuteTTS-0.3-500M"

# HF token from .env (for gated repos)
_HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN", "")


def venv_python() -> str:
    if sys.platform.startswith("win"):
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT).returncode


def _has_content(path: Path) -> bool:
    """True if path exists and contains at least one file (already downloaded)."""
    return path.exists() and any(path.rglob("*"))


def _download_kokoro(models_root: Path, force: bool = False) -> None:
    """Download Kokoro-82M model via huggingface_hub."""
    dest = models_root / "ml" / "kokoro"
    if not force and _has_content(dest):
        print(f"\n  Kokoro-82M already present at {dest} — skipping (use --force to re-download).")
        return
    from huggingface_hub import snapshot_download
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\n  Downloading Kokoro-82M (~300 MB) to {dest}...")
    kwargs = {"repo_id": _KOKORO_HF_REPO, "local_dir": str(dest), "tqdm_class": None}
    if _HF_TOKEN:
        kwargs["token"] = _HF_TOKEN
    snapshot_download(**kwargs)
    print(f"  ✓ Kokoro-82M download complete → {dest}")


def _download_piper(models_root: Path, stacks_yaml: Path, force: bool = False) -> None:
    """Download Piper voices. If stacks.yaml lists voices, download all; otherwise prompt."""
    from huggingface_hub import hf_hub_download

    dest = models_root / "ml" / "piper"
    dest.mkdir(parents=True, exist_ok=True)

    # Read voice list from stacks.yaml
    with open(stacks_yaml, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    voice_ids: list[str] = []
    for stack in catalog.get("stacks", []):
        if stack["id"] == "ml":
            for model in stack.get("models", []):
                if model["id"] == "piper":
                    voice_ids = [v["id"] for v in model.get("voices", [])]
                    break

    if not voice_ids:
        print("\n  No Piper voices defined in stacks.yaml.")
        return

    # Check which are already downloaded
    existing = [] if force else [v for v in voice_ids if (dest / f"{v}.onnx").exists()]
    to_download = [v for v in voice_ids if v not in existing]

    if existing:
        print(f"\n  Already downloaded: {', '.join(existing)}")
    if not to_download:
        print("  All Piper voices already installed.")
        return

    print(f"\n  Available Piper voices ({len(to_download)} remaining):")
    for i, vid in enumerate(to_download, 1):
        print(f"    {i}. {vid}")

    choice = input("\n  Download all? [Y/n] ").strip().lower()
    if choice == "n":
        print("  Skipped.")
        return

    selected = to_download  # download all for simplicity

    total = len(selected) * 2  # .onnx + .json per voice
    done = 0
    for vid in selected:
        parts = vid.split("-")
        if len(parts) >= 3:
            lang_full = parts[0]
            name = "-".join(parts[1:-1])
            quality = parts[-1]
            lang_short = lang_full.split("_")[0]
            subpath = f"{lang_short}/{lang_full}/{name}/{quality}"
        else:
            subpath = vid

        for ext in (f"{vid}.onnx", f"{vid}.onnx.json"):
            mb_done = done * 100 // total
            print(f"  [{mb_done}%] Downloading {ext}...")
            try:
                hf_hub_download(
                    repo_id=_PIPER_HF_REPO,
                    filename=f"{subpath}/{ext}",
                    local_dir=str(dest),
                    local_dir_use_symlinks=False,
                )
                done += 1
            except Exception as exc:
                print(f"  ✗ failed to download {ext}: {exc}")


def _download_auto(models_root: Path, model_id: str, force: bool = False) -> None:
    """Download models that use from_pretrained() — snapshot their HF repos."""
    # Map of model_id -> (HF repo, approximate size)
    downloads = {
        "chatterbox": (_CHATTERBOX_HF_REPO, "~2 GB"),
        "dia": (_DIA_HF_REPO, "~3.5 GB"),
        "f5tts": (_F5TTS_HF_REPO, "~1.2 GB"),
        "outetts": (_OUTETTS_HF_REPO, "~1 GB"),
    }
    if model_id not in downloads:
        print(f"  ⊘ No download strategy for '{model_id}'.")
        return

    repo, size = downloads[model_id]
    dest = models_root / "ml" / model_id
    if not force and _has_content(dest):
        print(f"\n  {model_id} already present at {dest} — skipping (use --force to re-download).")
        return
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\n  Downloading {model_id} from {repo} (~{size}) to {dest}...")
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=repo,
        local_dir=str(dest),
        tqdm_class=None,
    )
    print(f"  ✓ {model_id} download complete → {dest}")

    if model_id == "f5tts":
        _provision_f5tts_reference_voice(dest)


def _provision_f5tts_reference_voice(f5tts_dest: Path) -> None:
    """F5-TTS is zero-shot voice cloning — it needs a reference .wav + .txt
    per preset voice (see f5tts_engine.py's _VOICES), which snapshot_download()
    above doesn't provide (those aren't part of the model repo). The pip
    package itself bundles one usable English reference clip + transcript
    (infer/examples/basic/basic_ref_en.wav) — copy it in as the "en_female_calm"
    preset so at least one voice works out of the box. "en_male_warm" still
    needs its own reference audio sourced separately (not bundled anywhere).
    """
    try:
        import f5_tts
        bundled_wav = Path(f5_tts.__file__).parent / "infer" / "examples" / "basic" / "basic_ref_en.wav"
        if not bundled_wav.exists():
            print("  (f5tts bundled reference audio not found — preset voices need manual setup)")
            return
        voices_dir = f5tts_dest / "voices"
        voices_dir.mkdir(exist_ok=True)
        dest_wav = voices_dir / "en_female_calm.wav"
        dest_txt = voices_dir / "en_female_calm.txt"
        if not dest_wav.exists():
            import shutil as _shutil
            _shutil.copy(bundled_wav, dest_wav)
            dest_txt.write_text(
                "Some call me nature, others call me mother nature.", encoding="utf-8",
            )
            print(f"  ✓ Provisioned en_female_calm reference voice → {dest_wav}")
    except Exception as exc:
        print(f"  (could not provision f5tts reference voice: {exc})")


def _check_and_offer_models(models_root: Path, stacks_yaml: Path, force: bool = False) -> None:
    """Check which ML models are missing and offer to download them."""
    with open(stacks_yaml, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    missing: list[tuple[str, str]] = []  # (model_id, weights_subpath)
    for stack in catalog.get("stacks", []):
        if stack["id"] != "ml":
            continue
        for model in stack.get("models", []):
            mid = model["id"]
            wsub = model.get("weights_subpath", "")
            if not wsub:
                continue  # SAPI5 etc. have no weights
            path = models_root / wsub
            if not path.exists():
                missing.append((mid, wsub))

    if not missing:
        print("\n  All ML model weights are present.")
        return

    print(f"\n  Missing {len(missing)} ML model(s):")
    for mid, wsub in missing:
        size = {"kokoro": "~300 MB", "piper": "~50–150 MB/voice", "chatterbox": "~2 GB",
                "dia": "~3.5 GB", "f5tts": "~1.2 GB", "outetts": "~1 GB"}.get(mid, "?")
        print(f"    ⊘ {mid:12s}  ({size})  → .models/{wsub}")

    choice = input("\n  Download now? [Y/n] ").strip().lower()
    if choice == "n":
        print("  Skipped. Run `python setup.py download` later.")
        return

    print("\n  Starting download...")
    cmd_download_models(models_root, stacks_yaml, force=force)


def cmd_download_models(models_root: Path, stacks_yaml: Path, force: bool = False) -> None:
    """Download all ML model weights defined in stacks.yaml.

    Skips models whose weights_subpath already has content, unless force=True.
    """
    with open(stacks_yaml, encoding="utf-8") as f:
        catalog = yaml.safe_load(f)

    print("\nAlienVox Model Downloader")
    print("=" * 40)

    for stack in catalog.get("stacks", []):
        if stack["id"] != "ml":
            continue
        for model in stack.get("models", []):
            mid = model["id"]
            auto_dl = model.get("auto_download", False)

            if mid == "kokoro" and auto_dl:
                _download_kokoro(models_root, force=force)
            elif mid == "piper":
                _download_piper(models_root, stacks_yaml, force=force)
            elif auto_dl:
                _download_auto(models_root, mid, force=force)


# CUDA wheel index compatible with driver 12.4+ (torch's cu124 build works fine
# against newer drivers like 12.6 — CUDA is backward compatible at the driver level).
_TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"


def _detect_nvidia_gpu() -> bool:
    """True if an NVIDIA GPU + driver is present (nvidia-smi succeeds)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and "GPU" in result.stdout
    except Exception:
        return False


def _install_torch_for_hardware(python: str) -> None:
    """Install torch/torchaudio matching detected hardware.

    Plain `pip install torch` on Windows pulls the CPU-only wheel — an
    NVIDIA GPU sitting right there goes unused unless torch is installed
    from PyTorch's CUDA wheel index explicitly. Installing torch here
    *before* requirements.txt means requirements.txt's `torch>=2.0.0` is
    already satisfied and pip won't downgrade it to the CPU build.
    """
    if not _detect_nvidia_gpu():
        print("\nNo NVIDIA GPU detected (nvidia-smi not found or failed) — "
              "torch will install as CPU-only via requirements.txt.")
        return

    print(f"\nNVIDIA GPU detected — installing CUDA-enabled torch ({_TORCH_CUDA_INDEX})...")
    # --force-reinstall is required: pip treats an already-installed CPU
    # build (torch==2.6.0) as satisfying a plain "torch" requirement and
    # won't swap it for the +cu124 build otherwise. Deliberately NOT using
    # --no-deps — this runs before requirements.txt, so torch's own runtime
    # deps (sympy, jinja2, filelock, etc.) need to come from this install.
    rc = run([
        python, "-m", "pip", "install",
        "torch", "torchaudio",
        "--index-url", _TORCH_CUDA_INDEX,
        "--force-reinstall",
    ])
    if rc != 0:
        print("WARNING: CUDA torch install failed — falling back to CPU build via requirements.txt.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AlienVox python_app bootstrap")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["download"],
        help="'download' -- only download ML model weights (skip venv/pip install)",
    )
    parser.add_argument(
        "--download-models",
        action="store_true",
        help="(deprecated, use 'download' subcommand) Download ML model weights",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download model weights even if already present in .models/",
    )
    args = parser.parse_args()

    if args.command == "download" or args.download_models:
        models_root = ROOT / ".models"
        models_root.mkdir(exist_ok=True)
        cmd_download_models(models_root, ROOT / "stacks.yaml", force=args.force)
        return 0

    print("AlienVox python_app bootstrap")
    print(f"Python: {sys.version.splitlines()[0]}")

    if not VENV_DIR.exists():
        print(f"Creating venv at {VENV_DIR}...")
        if run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            print("ERROR: venv creation failed.")
            return 1
    else:
        print(f"Using existing venv at {VENV_DIR}")

    python = venv_python()
    print("\nUpgrading pip...")
    run([python, "-m", "pip", "install", "--upgrade", "pip"])

    _install_torch_for_hardware(python)

    req = ROOT / "requirements.txt"
    print(f"\nInstalling {req.name}...")
    print("(torch alone is ~2 GB on first install — this will take a while)")
    rc = run([python, "-m", "pip", "install", "-r", str(req)])
    if rc != 0:
        print("WARNING: Some packages failed. Check the output above.")

    print("\nInstalling Dia from source (no stable PyPI release)...")
    run([python, "-m", "pip", "install", "git+https://github.com/nari-labs/dia.git"])

    # Dia's own deps (nari-tts) pull numpy>=2.2.4, and some of its tree pulls
    # an old protobuf — both silently undo the pins requirements.txt set for
    # chatterbox-tts and onnx/onnxruntime (piper-tts's backend). Re-assert
    # them as the last install step so the final venv state is deterministic.
    print("\nRe-asserting numpy/protobuf pins (Dia's deps can override them)...")
    run([python, "-m", "pip", "install", "numpy<2.0.0", "protobuf>=4.25.8"])

    # ── Auto-detect missing models and offer download ───────────────────────
    models_root = ROOT / ".models"
    models_root.mkdir(exist_ok=True)
    _check_and_offer_models(models_root, ROOT / "stacks.yaml", force=args.force)

    print("\nBootstrap complete.")
    print(f"Activate venv:  {VENV_DIR}\\Scripts\\activate")
    print(f"\nTo download ML models later:  python setup.py download")
    print("Run app:        python -m src.main")
    return 0


if __name__ == "__main__":
    # Windows consoles often default to cp1252, which can't encode the
    # checkmark/arrow characters used throughout this script's progress output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
