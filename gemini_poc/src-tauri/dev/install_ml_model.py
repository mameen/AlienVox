from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PIPER_REPO = "rhasspy/piper-voices"
PIPER_REVISION = "v1.0.0"
PIPER_FILES = [
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx",
    "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
]

SNAPSHOT_MODELS = {
    "vibevoice-realtime-0.5b": {
        "repo_id": "microsoft/VibeVoice-Realtime-0.5B",
        "local_name": "vibevoice-realtime-0.5b",
    },
    "zonos2": {
        "repo_id": "Zyphra/ZONOS2",
        "local_name": "zonos2",
    },
    "dia": {
        "repo_id": "nari-labs/Dia-1.6B-0626",
        "local_name": "dia",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install AlienVox local ML models")
    parser.add_argument("--model", required=True)
    parser.add_argument("--models-root", required=True)
    parser.add_argument("--hf-home", required=True)
    return parser.parse_args()


def ensure_huggingface_hub() -> None:
    try:
        import huggingface_hub  # noqa: F401
        return
    except Exception:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "huggingface_hub[hf_xet]"]
        )


def write_manifest(path: Path, payload: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "alienvox-install.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def install_kokoro(models_root: Path, hf_home: Path) -> None:
    import os

    os.environ["HF_HOME"] = str(hf_home)
    from kokoro import KPipeline

    KPipeline(lang_code="a")
    write_manifest(
        models_root / "kokoro",
        {
            "id": "kokoro",
            "repo_id": "hexgrad/Kokoro-82M",
            "kind": "runtime-cache",
            "status": "installed",
        },
    )


def install_piper(models_root: Path) -> None:
    from huggingface_hub import hf_hub_download

    target = models_root / "piper"
    target.mkdir(parents=True, exist_ok=True)
    for remote in PIPER_FILES:
        downloaded = Path(
            hf_hub_download(
                repo_id=PIPER_REPO,
                filename=remote,
                revision=PIPER_REVISION,
                repo_type="model",
            )
        )
        local = target / downloaded.name
        local.write_bytes(downloaded.read_bytes())
    write_manifest(
        target,
        {
            "id": "piper",
            "repo_id": PIPER_REPO,
            "revision": PIPER_REVISION,
            "voice": "en_US-lessac-medium",
            "status": "installed",
        },
    )


def install_snapshot(model: str, models_root: Path) -> None:
    from huggingface_hub import snapshot_download

    spec = SNAPSHOT_MODELS[model]
    target = models_root / spec["local_name"]
    snapshot_download(
        repo_id=spec["repo_id"],
        local_dir=target,
        local_dir_use_symlinks=False,
        resume_download=True,
    )
    write_manifest(
        target,
        {
            "id": model,
            "repo_id": spec["repo_id"],
            "kind": "huggingface-snapshot",
            "status": "installed",
        },
    )


def main() -> int:
    args = parse_args()
    model = args.model.strip() or "kokoro"
    models_root = Path(args.models_root)
    hf_home = Path(args.hf_home)
    models_root.mkdir(parents=True, exist_ok=True)
    hf_home.mkdir(parents=True, exist_ok=True)

    ensure_huggingface_hub()

    if model == "kokoro":
        install_kokoro(models_root, hf_home)
    elif model == "piper":
        install_piper(models_root)
    elif model in SNAPSHOT_MODELS:
        install_snapshot(model, models_root)
    else:
        raise SystemExit(f"unknown ML model: {model}")

    print(f"Installed {model} under {models_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
