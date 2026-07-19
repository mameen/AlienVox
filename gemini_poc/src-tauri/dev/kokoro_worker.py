from __future__ import annotations

import json
import os
import sys
import threading
import time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("TORCH_NUM_THREADS", "2")

SAMPLE_RATE = 24000


class State:
    last_activity = time.monotonic()
    speaking = False


def idle_watchdog(ttl_seconds: int) -> None:
    while True:
        time.sleep(1)
        idle_for = time.monotonic() - State.last_activity
        if not State.speaking and idle_for > ttl_seconds:
            print(f"Kokoro worker idle for {idle_for:.1f}s; exiting", file=sys.stderr, flush=True)
            os._exit(0)


def scaled_float32(audio, volume_percent: int):
    import numpy as np

    samples = np.asarray(audio, dtype=np.float32)
    volume = max(0.0, min(1.0, volume_percent / 100.0))
    return np.clip(samples * volume, -1.0, 1.0)


def unix_ms() -> int:
    return time.time_ns() // 1_000_000


def emit_telemetry(event: str, request: dict, status: str = "ok", detail: str = "") -> None:
    requested_at = int(request.get("requested_at_unix_ms") or unix_ms())
    now = unix_ms()
    payload = {
        "timestampUnixMs": now,
        "event": event,
        "requestId": str(request.get("telemetry_request_id") or ""),
        "engine": "ml",
        "model": "kokoro",
        "voice": str(request.get("voice") or "af_heart"),
        "textChars": int(request.get("text_chars") or 0),
        "textBytes": int(request.get("text_bytes") or 0),
        "config": {
            "rate": int(request.get("rate") or 0),
            "pitch": int(request.get("pitch") or 0),
            "volume": int(request.get("volume") or 100),
            "hotTtlSeconds": int(request.get("hot_ttl_seconds") or 0),
        },
        "latencyMs": max(0, now - requested_at),
        "status": status,
        "detail": detail or None,
    }
    print(f"ALIENVOX_TELEMETRY {json.dumps(payload, separators=(',', ':'))}", file=sys.stderr, flush=True)


def play_audio_chunks(chunks, volume_percent: int, request: dict) -> None:
    import sounddevice as sd

    first = True
    for audio in chunks:
        if first:
            emit_telemetry("tts.first_audio", request)
            first = False
        sd.play(scaled_float32(audio, volume_percent), SAMPLE_RATE, blocking=True)


def main() -> int:
    ttl = int(os.environ.get("ALIENVOX_KOKORO_TTL_SECONDS", "30"))
    threading.Thread(target=idle_watchdog, args=(ttl,), daemon=True).start()

    try:
        from kokoro import KPipeline
        import torch

        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
    except Exception as exc:
        print(f"Kokoro worker dependency failure: {exc}", file=sys.stderr, flush=True)
        return 2

    print(f"Kokoro worker loading pipeline; ttl={ttl}s", file=sys.stderr, flush=True)
    pipeline = KPipeline(lang_code="a")
    print("Kokoro worker ready", file=sys.stderr, flush=True)

    for line in sys.stdin:
        State.last_activity = time.monotonic()
        try:
            request = json.loads(line)
            text = str(request.get("text", "")).strip()
            voice = str(request.get("voice") or "af_heart")
            rate = int(request.get("rate", 0))
            volume = int(request.get("volume", 100))
        except Exception as exc:
            print(f"Kokoro worker bad request: {exc}", file=sys.stderr, flush=True)
            continue

        if not text:
            continue

        speed = max(0.5, min(2.0, 1.0 + (rate / 20.0)))
        try:
            State.speaking = True
            emit_telemetry("tts.synthesis_start", request)
            print(f"Kokoro worker speaking voice={voice}", file=sys.stderr, flush=True)
            chunks = [
                audio
                for _graphemes, _phonemes, audio in pipeline(
                    text, voice=voice, speed=speed
                )
            ]
            play_audio_chunks(chunks, volume, request)
            emit_telemetry("tts.playback_end", request)
            print("Kokoro worker playback finished", file=sys.stderr, flush=True)
        except Exception as exc:
            emit_telemetry("tts.error", request, status="error", detail=str(exc))
            print(f"Kokoro worker synthesis/playback failed: {exc}", file=sys.stderr, flush=True)
        finally:
            State.speaking = False
            State.last_activity = time.monotonic()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
