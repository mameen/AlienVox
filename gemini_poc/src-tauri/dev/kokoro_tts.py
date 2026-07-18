from __future__ import annotations

import argparse
import os
import sys
import wave
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("TORCH_NUM_THREADS", "2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AlienVox local Kokoro dev TTS runner")
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--rate", type=int, default=0)
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--volume", type=int, default=100)
    parser.add_argument("--output-wav", default="")
    return parser.parse_args()


def fail_missing_deps(error: Exception) -> int:
    print("Kokoro dev TTS dependencies are not installed.", file=sys.stderr)
    print("Install them inside gemini_poc/.venv, then retry:", file=sys.stderr)
    print(r"  .\.venv\Scripts\python.exe -m pip install kokoro soundfile", file=sys.stderr)
    print(f"Import error: {error}", file=sys.stderr)
    return 2


def write_wav(path: Path, audio, sample_rate: int = 24000, volume_percent: int = 100) -> None:
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - dependency guidance path
        raise RuntimeError("numpy is required by the Kokoro audio writer") from exc

    samples = np.asarray(audio, dtype=np.float32)
    volume = max(0.0, min(1.0, volume_percent / 100.0))
    samples = samples * volume
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def scaled_float32(audio, volume_percent: int):
    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - dependency guidance path
        raise RuntimeError("numpy is required by the Kokoro audio player") from exc

    samples = np.asarray(audio, dtype=np.float32)
    volume = max(0.0, min(1.0, volume_percent / 100.0))
    return np.clip(samples * volume, -1.0, 1.0)


def play_audio_chunks(chunks, volume_percent: int, sample_rate: int = 24000) -> None:
    try:
        import sounddevice as sd
    except Exception as exc:
        print("Direct audio playback requires sounddevice.", file=sys.stderr)
        print(r"Install it inside gemini_poc/.venv:", file=sys.stderr)
        print(r"  .\.venv\Scripts\python.exe -m pip install sounddevice", file=sys.stderr)
        raise exc

    for audio in chunks:
        samples = scaled_float32(audio, volume_percent)
        sd.play(samples, sample_rate, blocking=True)


def main() -> int:
    args = parse_args()
    text = Path(args.text_file).read_text(encoding="utf-8").strip()
    if not text:
        return 0

    try:
        from kokoro import KPipeline
        import torch

        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
    except Exception as exc:
        return fail_missing_deps(exc)

    pipeline = KPipeline(lang_code="a")
    speed = max(0.5, min(2.0, 1.0 + (args.rate / 20.0)))

    try:
        print("Kokoro synthesis started", file=sys.stderr, flush=True)
        generator = pipeline(text, voice=args.voice or "af_heart", speed=speed)
        chunks = []
        for _graphemes, _phonemes, audio in generator:
            chunks.append(audio)
        if not chunks:
            return 0
        if args.output_wav:
            try:
                import numpy as np
            except Exception as exc:
                print(f"WAV export failed: {exc}", file=sys.stderr)
                return 1
            wav_path = Path(args.output_wav)
            combined = np.concatenate([scaled_float32(chunk, args.volume) for chunk in chunks])
            write_wav(wav_path, combined, volume_percent=100)
            print(f"Exported {wav_path}", file=sys.stderr, flush=True)
        else:
            print(f"Playing {len(chunks)} Kokoro chunk(s) directly", file=sys.stderr, flush=True)
            play_audio_chunks(chunks, args.volume)
        print("Playback finished", file=sys.stderr, flush=True)
    except Exception as exc:
        print(f"Kokoro synthesis/playback failed: {exc}", file=sys.stderr)
        return 1
    finally:
        Path(args.text_file).unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
