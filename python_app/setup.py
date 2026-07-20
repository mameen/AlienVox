"""AlienVox python_app bootstrap — creates venv, installs requirements, and downloads ML models."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
import yaml

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"

# Load .env so HF_TOKEN is available for gated repos
_load_dotenv = load_dotenv(ROOT / ".env", override=False)

# HuggingFace repos (must match install_dialog.py and engine source files)
_KOKORO_HF_REPO = "hexgrad/Kokoro-82M"
_PIPER_HF_REPO = "rhasspy/piper-voices"
_CHATTERBOX_HF_REPO = "ResembleAI/chatterbox"
_DIA_HF_REPO = "nari-labs/Dia-1.6B"
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


def _download_kokoro(models_root: Path) -> None:
    """Download Kokoro-82M model via huggingface_hub."""
    from huggingface_hub import snapshot_download
    dest = models_root / "ml" / "kokoro"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\n  Downloading Kokoro-82M (~300 MB) to {dest}...")
    kwargs = {"repo_id": _KOKORO_HF_REPO, "local_dir": str(dest), "tqdm_class": None}
    if _HF_TOKEN:
        kwargs["token"] = _HF_TOKEN
    snapshot_download(**kwargs)
    print(f"  ✓ Kokoro-82M download complete → {dest}")


def _download_piper(models_root: Path, stacks_yaml: Path) -> None:
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
    existing = [v for v in voice_ids if (dest / f"{v}.onnx").exists()]
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


def _download_auto(models_root: Path, model_id: str) -> None:
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
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\n  Downloading {model_id} from {repo} (~{size}) to {dest}...")
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=repo,
        local_dir=str(dest),
        tqdm_class=None,
    )
    print(f"  ✓ {model_id} download complete → {dest}")


def _check_and_offer_models(models_root: Path, stacks_yaml: Path) -> None:
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
        print("  Skipped. Run `python setup.py --download-models` later.")
        return

    print("\n  Starting download...")
    cmd_download_models(models_root, stacks_yaml)


def cmd_download_models(models_root: Path, stacks_yaml: Path) -> None:
    """Download all ML model weights defined in stacks.yaml."""
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
                _download_kokoro(models_root)
            elif mid == "piper":
                _download_piper(models_root, stacks_yaml)
            elif auto_dl:
                _download_auto(models_root, mid)


def main() -> int:
    parser = argparse.ArgumentParser(description="AlienVox python_app bootstrap")
    parser.add_argument(
        "--download-models",
        action="store_true",
        help="Download ML model weights defined in stacks.yaml",
    )
    args = parser.parse_args()

    if args.download_models:
        models_root = ROOT / ".models"
        models_root.mkdir(exist_ok=True)
        cmd_download_models(models_root, ROOT / "stacks.yaml")
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

    req = ROOT / "requirements.txt"
    print(f"\nInstalling {req.name}...")
    print("(torch alone is ~2 GB on first install — this will take a while)")
    rc = run([python, "-m", "pip", "install", "-r", str(req)])
    if rc != 0:
        print("WARNING: Some packages failed. Check the output above.")

    print("\nInstalling Dia from source (no stable PyPI release)...")
    run([python, "-m", "pip", "install", "git+https://github.com/nari-labs/dia.git"])

    # ── Auto-detect missing models and offer download ───────────────────────
    models_root = ROOT / ".models"
    models_root.mkdir(exist_ok=True)
    _check_and_offer_models(models_root, ROOT / "stacks.yaml")

    print("\nBootstrap complete.")
    print(f"Activate venv:  {VENV_DIR}\\Scripts\\activate")
    print(f"\nTo download ML models manually:  python setup.py --download-models")
    print("Run app:        python -m src.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
