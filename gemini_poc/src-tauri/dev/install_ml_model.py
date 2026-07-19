from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path


def _dir_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def _emit(pct: int, msg: str) -> None:
    print(f"PROGRESS {max(0, min(100, pct))} {msg}", flush=True)


def _repo_total_bytes(repo_id: str) -> int:
    try:
        from huggingface_hub import HfApi

        info = HfApi().repo_info(repo_id, files_metadata=True)
        return sum(int(getattr(s, "size", 0) or 0) for s in (info.siblings or []))
    except Exception:
        return 0


def _start_progress_poller(
    target: Path, total_bytes: int, label: str, stop: threading.Event
) -> None:
    def loop() -> None:
        while not stop.is_set():
            got = _dir_bytes(target)
            if total_bytes > 0:
                pct = int((got / total_bytes) * 95)  # cap live at 95, jump to 100 on success
                _emit(pct, f"{label}: {got // (1024*1024)} / {total_bytes // (1024*1024)} MB")
            else:
                _emit(5, f"{label}: {got // (1024*1024)} MB")
            stop.wait(1.5)

    threading.Thread(target=loop, daemon=True).start()


PIPER_REPO = "rhasspy/piper-voices"
PIPER_REVISION = "v1.0.0"

# Full catalog of available Piper voices.
# Each entry: voice_id -> { files: [(remote, dest), ...], gender, lang, quality }
# Paths are relative to rhasspy/piper-voices@v1.0.0.
PIPER_VOICES: dict[str, dict] = {
    "en_US-lessac-medium": {
        "files": [
            ("en/en_US/lessac/medium/en_US-lessac-medium.onnx",      "en_US-lessac-medium.onnx"),
            ("en/en_US/lessac/medium/en_US-lessac-medium.onnx.json", "en_US-lessac-medium.onnx.json"),
        ],
        "gender": "M", "lang": "en-US", "quality": "medium",
    },
    "en_US-amy-medium": {
        "files": [
            ("en/en_US/amy/medium/en_US-amy-medium.onnx",      "en_US-amy-medium.onnx"),
            ("en/en_US/amy/medium/en_US-amy-medium.onnx.json", "en_US-amy-medium.onnx.json"),
        ],
        "gender": "F", "lang": "en-US", "quality": "medium",
    },
    "en_US-ryan-high": {
        "files": [
            ("en/en_US/ryan/high/en_US-ryan-high.onnx",      "en_US-ryan-high.onnx"),
            ("en/en_US/ryan/high/en_US-ryan-high.onnx.json", "en_US-ryan-high.onnx.json"),
        ],
        "gender": "M", "lang": "en-US", "quality": "high",
    },
    "en_US-kathleen-low": {
        "files": [
            ("en/en_US/kathleen/low/en_US-kathleen-low.onnx",      "en_US-kathleen-low.onnx"),
            ("en/en_US/kathleen/low/en_US-kathleen-low.onnx.json", "en_US-kathleen-low.onnx.json"),
        ],
        "gender": "F", "lang": "en-US", "quality": "low",
    },
    "en_GB-southern_english_female-medium": {
        "files": [
            ("en/en_GB/southern_english_female/medium/en_GB-southern_english_female-medium.onnx",      "en_GB-southern_english_female-medium.onnx"),
            ("en/en_GB/southern_english_female/medium/en_GB-southern_english_female-medium.onnx.json", "en_GB-southern_english_female-medium.onnx.json"),
        ],
        "gender": "F", "lang": "en-GB", "quality": "medium",
    },
    "en_GB-jenny_dioco-medium": {
        "files": [
            ("en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx",      "en_GB-jenny_dioco-medium.onnx"),
            ("en/en_GB/jenny_dioco/medium/en_GB-jenny_dioco-medium.onnx.json", "en_GB-jenny_dioco-medium.onnx.json"),
        ],
        "gender": "F", "lang": "en-GB", "quality": "medium",
    },
    "en_GB-alan-medium": {
        "files": [
            ("en/en_GB/alan/medium/en_GB-alan-medium.onnx",      "en_GB-alan-medium.onnx"),
            ("en/en_GB/alan/medium/en_GB-alan-medium.onnx.json", "en_GB-alan-medium.onnx.json"),
        ],
        "gender": "M", "lang": "en-GB", "quality": "medium",
    },
}

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
    parser.add_argument("--voices", default="",
                        help="Comma-separated list of Piper voice ids to install. "
                             "Empty = install all voices in catalog.")
    return parser.parse_args()


def ensure_huggingface_hub() -> None:
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        print(
            "ERROR: 'huggingface_hub' not installed.\n"
            "Run:  pip install -r requirements.txt  or rerun setup.py.",
            file=sys.stderr, flush=True,
        )
        raise


def write_manifest(path: Path, payload: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "alienvox-install.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def install_kokoro(models_root: Path, hf_home: Path) -> None:
    import os

    os.environ["HF_HOME"] = str(hf_home)
    _emit(5, "Loading Kokoro pipeline (first run downloads weights)")
    stop = threading.Event()
    _start_progress_poller(hf_home, _repo_total_bytes("hexgrad/Kokoro-82M"), "kokoro", stop)
    try:
        from kokoro import KPipeline
        KPipeline(lang_code="a")
    finally:
        stop.set()
        time.sleep(0.1)
    _emit(99, "Finalizing kokoro")
    write_manifest(
        models_root / "kokoro",
        {
            "id": "kokoro",
            "repo_id": "hexgrad/Kokoro-82M",
            "kind": "runtime-cache",
            "status": "installed",
        },
    )


def install_piper(models_root: Path, voices: list[str]) -> None:
    from huggingface_hub import hf_hub_download

    # Resolve which voices to install.
    selected = [v for v in voices if v in PIPER_VOICES] if voices else list(PIPER_VOICES.keys())
    if not selected:
        _emit(0, f"Unknown voice(s) {voices}; available: {list(PIPER_VOICES.keys())}")
        return

    target = models_root / "piper"
    target.mkdir(parents=True, exist_ok=True)

    # Build flat file list for selected voices.
    all_files = [(remote, dest) for vid in selected for remote, dest in PIPER_VOICES[vid]["files"]]
    total = max(1, len(all_files))
    for i, (remote, dest_name) in enumerate(all_files):
        _emit(int(5 + (i / total) * 90), f"Downloading {dest_name}")
        try:
            downloaded = Path(
                hf_hub_download(
                    repo_id=PIPER_REPO,
                    filename=remote,
                    revision=PIPER_REVISION,
                    repo_type="model",
                )
            )
            (target / dest_name).write_bytes(downloaded.read_bytes())
        except Exception as e:
            _emit(int(5 + (i / total) * 90), f"WARNING: {dest_name} skipped — {e}")

    _emit(99, "Finalizing piper")
    installed_voices = [vid for vid in selected if (target / f"{vid}.onnx").exists()]
    write_manifest(
        target,
        {
            "id": "piper",
            "repo_id": PIPER_REPO,
            "revision": PIPER_REVISION,
            "voices": installed_voices,
            "status": "installed",
        },
    )


def install_snapshot(model: str, models_root: Path) -> None:
    from huggingface_hub import snapshot_download

    spec = SNAPSHOT_MODELS[model]
    target = models_root / spec["local_name"]
    target.mkdir(parents=True, exist_ok=True)

    _emit(1, f"Resolving {spec['repo_id']}")
    total = _repo_total_bytes(spec["repo_id"])
    stop = threading.Event()
    _start_progress_poller(target, total, spec["local_name"], stop)

    try:
        snapshot_download(
            repo_id=spec["repo_id"],
            local_dir=target,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    finally:
        stop.set()
        time.sleep(0.1)

    _emit(99, f"Finalizing {spec['local_name']}")
    write_manifest(
        target,
        {
            "id": model,
            "repo_id": spec["repo_id"],
            "kind": "huggingface-snapshot",
            "status": "installed",
        },
    )
    _emit(100, f"Installed {spec['local_name']}")


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
        voices = [v.strip() for v in args.voices.split(",") if v.strip()] if args.voices else []
        install_piper(models_root, voices)
    elif model in SNAPSHOT_MODELS:
        install_snapshot(model, models_root)
    else:
        raise SystemExit(f"unknown ML model: {model}")

    print(f"Installed {model} under {models_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
