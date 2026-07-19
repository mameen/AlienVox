from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlienVox local Piper dev TTS runner")
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--hot-ttl-seconds", type=int, default=0)
    parser.add_argument("--voice", default="")
    # Piper-specific runtime knobs (upstream docs: rhasspy/piper CLI).
    parser.add_argument("--length-scale", type=float, default=None,
                        help="Overrides rate-derived length scale (>1 = slower).")
    parser.add_argument("--noise-scale", type=float, default=0.667,
                        help="Prosody / expressiveness variability (0..1).")
    parser.add_argument("--noise-w", type=float, default=0.8,
                        help="Speaking-style variation (0..1).")
    parser.add_argument("--sentence-silence", type=float, default=0.2,
                        help="Seconds of silence inserted between sentences.")
    parser.add_argument("--speaker", type=int, default=-1,
                        help="Speaker id for multi-speaker models; -1 = default.")
    parser.add_argument("--output-wav", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--telemetry-request-id", default="")
    parser.add_argument("--requested-at-unix-ms", type=int, default=0)
    parser.add_argument("--text-chars", type=int, default=0)
    parser.add_argument("--text-bytes", type=int, default=0)
    return parser.parse_args()


def sample_rate(config_path: Path) -> int:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return int(config.get("audio", {}).get("sample_rate", 22050))
    except Exception:
        return 22050


def unix_ms() -> int:
    return time.time_ns() // 1_000_000


def emit_telemetry(event: str, args: argparse.Namespace, status: str = "ok", detail: str = "") -> None:
    requested_at = args.requested_at_unix_ms or unix_ms()
    now = unix_ms()
    payload = {
        "timestampUnixMs": now,
        "event": event,
        "sessionId": args.session_id,
        "playId": args.telemetry_request_id,
        "requestId": args.telemetry_request_id,
        "engine": "ml",
        "model": "piper",
        "voice": args.voice or "en_US-lessac-medium",
        "textChars": args.text_chars,
        "textBytes": args.text_bytes,
        "config": {
            "rate": args.rate,
            "pitch": 0,
            "volume": args.volume,
            "hotTtlSeconds": args.hot_ttl_seconds,
        },
        "latencyMs": max(0, now - requested_at),
        "status": status,
        "detail": detail or None,
    }
    print(f"ALIENVOX_TELEMETRY {json.dumps(payload, separators=(',', ':'))}", file=sys.stderr, flush=True)


def play_raw_pcm(raw: bytes, rate: int, volume_percent: int, args: argparse.Namespace) -> None:
    import numpy as np
    import sounddevice as sd

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    volume = max(0.0, min(1.0, volume_percent / 100.0))
    emit_telemetry("tts.first_audio", args)
    sd.play(np.clip(samples * volume, -1.0, 1.0), rate, blocking=True)
    emit_telemetry("tts.playback_end", args)


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

    length_scale = (
        args.length_scale
        if args.length_scale is not None
        else max(0.5, min(2.0, 1.0 - (args.rate / 30.0)))
    )
    base_cmd = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        str(model_path),
        "--config",
        str(config_path),
        "--length-scale",
        str(length_scale),
        "--noise-scale",
        str(max(0.0, min(1.0, args.noise_scale))),
        "--noise-w",
        str(max(0.0, min(1.0, args.noise_w))),
        "--sentence-silence",
        str(max(0.0, min(5.0, args.sentence_silence))),
        "--volume",
        str(max(0.0, args.volume / 100.0)),
    ]
    if args.speaker >= 0:
        base_cmd.extend(["--speaker", str(args.speaker)])

    try:
        if args.output_wav:
            result = subprocess.run(
                [*base_cmd, "--output-file", args.output_wav],
                input=text,
                text=True,
            )
            return result.returncode

        emit_telemetry("tts.synthesis_start", args)
        result = subprocess.run(
            [*base_cmd, "--output-raw"],
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.stderr:
            print(result.stderr.decode("utf-8", errors="replace").strip(), file=sys.stderr)
        if result.returncode != 0:
            emit_telemetry("tts.error", args, status="error", detail=f"piper exited {result.returncode}")
            return result.returncode

        play_raw_pcm(result.stdout, sample_rate(config_path), args.volume, args)
        return 0
    finally:
        Path(args.text_file).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
