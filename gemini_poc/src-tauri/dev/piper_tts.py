from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlienVox local Piper dev TTS runner")
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--output-wav", default="")
    return parser.parse_args()


def sample_rate(config_path: Path) -> int:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return int(config.get("audio", {}).get("sample_rate", 22050))
    except Exception:
        return 22050


def play_raw_pcm(raw: bytes, rate: int, volume_percent: int) -> None:
    import numpy as np
    import sounddevice as sd

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    volume = max(0.0, min(1.0, volume_percent / 100.0))
    sd.play(np.clip(samples * volume, -1.0, 1.0), rate, blocking=True)


def main() -> int:
    args = parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        return 0

    model_path = Path(args.model)
    config_path = Path(args.config) if args.config else model_path.with_suffix(".onnx.json")
    if not model_path.exists():
        print(f"Piper model not found: {model_path}", file=sys.stderr)
        return 1

    base_cmd = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        str(model_path),
        "--config",
        str(config_path),
        "--length-scale",
        str(max(0.5, min(2.0, 1.0 - (args.rate / 30.0)))),
        "--volume",
        str(max(0.0, args.volume / 100.0)),
    ]

    try:
        if args.output_wav:
            result = subprocess.run(
                [*base_cmd, "--output-file", args.output_wav],
                input=text,
                text=True,
            )
            return result.returncode

        result = subprocess.run(
            [*base_cmd, "--output-raw"],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.stderr:
            print(result.stderr.decode("utf-8", errors="replace").strip(), file=sys.stderr)
        if result.returncode != 0:
            return result.returncode

        play_raw_pcm(result.stdout, sample_rate(config_path), args.volume)
        return 0
    finally:
        Path(args.text_file).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
