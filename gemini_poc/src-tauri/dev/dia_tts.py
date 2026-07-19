"""AlienVox runner for nari-labs/Dia-1.6B dialogue TTS.

Dia generates expressive speech from text marked with speaker tags [S1]/[S2].
This runner wraps a single speaker ([S1]) call and plays the result.

Requires:
    pip install git+https://github.com/nari-labs/dia.git sounddevice
    (dac is a transitive dependency pulled in by dia)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlienVox Dia TTS runner")
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--rate",   type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--output-wav", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--telemetry-request-id", default="")
    parser.add_argument("--requested-at-unix-ms", type=int, default=0)
    parser.add_argument("--text-chars", type=int, default=0)
    parser.add_argument("--text-bytes", type=int, default=0)
    return parser.parse_args()


def unix_ms() -> int:
    return time.time_ns() // 1_000_000


def emit_telemetry(event: str, args: argparse.Namespace, status: str = "ok", detail: str = "") -> None:
    requested_at = args.requested_at_unix_ms or unix_ms()
    now = unix_ms()
    payload = {
        "timestampUnixMs": now,
        "event": event,
        "sessionId": args.session_id,
        "requestId": args.telemetry_request_id,
        "engine": "ml",
        "model": "dia",
        "voice": "dia-s1",
        "textChars": args.text_chars,
        "textBytes": args.text_bytes,
        "latencyMs": max(0, now - requested_at),
        "status": status,
        "detail": detail or None,
    }
    print(f"ALIENVOX_TELEMETRY {json.dumps(payload, separators=(',', ':'))}", file=sys.stderr, flush=True)


def ensure_dia() -> None:
    try:
        import dia  # noqa: F401
    except ImportError:
        print(
            "ERROR: 'dia' package not installed.\n"
            "Run:  pip install git+https://github.com/nari-labs/dia.git\n"
            "or rerun setup.py to install all requirements.",
            file=sys.stderr, flush=True,
        )
        raise


def main() -> int:
    args = parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        return 0

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        print(f"Dia model directory not found: {model_dir}", file=sys.stderr)
        return 1

    ensure_dia()

    emit_telemetry("tts.synthesis_start", args)
    try:
        from dia.model import Dia

        # Load from local snapshot directory.
        model = Dia.from_pretrained(str(model_dir), compute_dtype="float32")

        # Dia expects dialogue markup; wrap in [S1] for single-speaker output.
        prompt = f"[S1] {text}"
        samples = model.generate(prompt, use_torch_compile=False, verbose=False)

        sample_rate = 44100  # Dia outputs at 44100 Hz

        if args.output_wav:
            try:
                import soundfile as sf
                sf.write(args.output_wav, samples, sample_rate)
            except ImportError:
                import wave, struct
                flat = [int(x * 32767) for x in samples.flatten()]
                with wave.open(args.output_wav, "w") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    wf.writeframes(struct.pack(f"<{len(flat)}h", *flat))
            emit_telemetry("tts.playback_end", args)
            return 0

        import numpy as np
        import sounddevice as sd

        audio = np.array(samples, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=0)
        volume = max(0.0, min(1.0, args.volume / 100.0))
        emit_telemetry("tts.first_audio", args)
        sd.play(np.clip(audio * volume, -1.0, 1.0), sample_rate, blocking=True)
        emit_telemetry("tts.playback_end", args)
        return 0

    except Exception as exc:
        emit_telemetry("tts.error", args, status="error", detail=str(exc))
        print(f"Dia inference failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            Path(args.text_file).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
