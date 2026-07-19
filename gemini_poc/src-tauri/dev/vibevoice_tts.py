"""AlienVox runner for microsoft/VibeVoice-Realtime-0.5B streaming TTS.

VibeVoice-Realtime is a small (0.5 B) streaming TTS model from Microsoft Research.
It generates audio via a language-model backbone + codec (SoundStream / EnCodec).

Requires:
    pip install transformers torch sounddevice accelerate
    (codec dependencies are pulled in by transformers extras)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlienVox VibeVoice TTS runner")
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
        "model": "vibevoice-realtime-0.5b",
        "voice": "vibevoice-default",
        "textChars": args.text_chars,
        "textBytes": args.text_bytes,
        "latencyMs": max(0, now - requested_at),
        "status": status,
        "detail": detail or None,
    }
    print(f"ALIENVOX_TELEMETRY {json.dumps(payload, separators=(',', ':'))}", file=sys.stderr, flush=True)


def ensure_deps() -> None:
    missing = []
    for pkg in ("transformers", "torch", "accelerate"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(
            f"ERROR: Missing packages: {missing}\n"
            "Run:  pip install -r requirements.txt\n"
            "or rerun setup.py to install all requirements.",
            file=sys.stderr, flush=True,
        )
        raise ImportError(f"Missing packages: {missing}")


def write_wav(path: str, samples, sample_rate: int) -> None:
    import numpy as np
    arr = np.array(samples, dtype=np.float32).flatten()
    pcm = (arr * 32767).clip(-32768, 32767).astype(np.int16)
    import wave, struct
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def main() -> int:
    args = parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        return 0

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        print(f"VibeVoice model directory not found: {model_dir}", file=sys.stderr)
        return 1

    ensure_deps()

    emit_telemetry("tts.synthesis_start", args)
    try:
        from transformers import pipeline, AutoProcessor, AutoModel
        import torch

        # Try the high-level pipeline first (works if model registers itself).
        try:
            tts = pipeline(
                "text-to-speech",
                model=str(model_dir),
                device="cpu",
            )
            result = tts(text)
            samples = result["audio"]
            sample_rate = result.get("sampling_rate", 24000)

        except Exception as pipeline_err:
            print(f"pipeline() fallback: {pipeline_err}", file=sys.stderr)
            # Manual load — read the model config to infer sampling rate.
            config_path = model_dir / "config.json"
            sample_rate = 24000
            if config_path.exists():
                cfg = json.loads(config_path.read_text())
                sample_rate = (
                    cfg.get("sampling_rate")
                    or cfg.get("audio_encoder", {}).get("sampling_rate")
                    or 24000
                )
            processor = AutoProcessor.from_pretrained(str(model_dir), local_files_only=True)
            model = AutoModel.from_pretrained(str(model_dir), local_files_only=True)
            model.eval()
            inputs = processor(text=text, return_tensors="pt")
            with torch.no_grad():
                output = model(**inputs)
            # Common output shapes: (1, 1, T) or (1, T)
            samples = output.audio_values if hasattr(output, "audio_values") else output[0]
            samples = samples.squeeze().cpu().float().numpy()

        import numpy as np
        audio = np.array(samples, dtype=np.float32).flatten()
        volume = max(0.0, min(1.0, args.volume / 100.0))

        if args.output_wav:
            write_wav(args.output_wav, audio * volume, sample_rate)
            emit_telemetry("tts.playback_end", args)
            return 0

        import sounddevice as sd
        emit_telemetry("tts.first_audio", args)
        sd.play(np.clip(audio * volume, -1.0, 1.0), sample_rate, blocking=True)
        emit_telemetry("tts.playback_end", args)
        return 0

    except Exception as exc:
        emit_telemetry("tts.error", args, status="error", detail=str(exc))
        print(f"VibeVoice inference failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            Path(args.text_file).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
