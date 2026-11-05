"""Generate canonical offline previews for Pocket, Supertonic 3, and MOSS TTS.

Run from ``python_app`` after installing the three model weights::

    .venv\\Scripts\\python.exe scripts/generate_lightweight_tts_samples.py
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.control.app_controller import SAMPLE_TEXT  # noqa: E402
from src.engines.base import SpeakParams  # noqa: E402
from src.engines.moss_tts_nano_engine import MossTtsNanoEngine  # noqa: E402
from src.engines.pockettts_engine import PocketTTSEngine  # noqa: E402
from src.engines.supertonic3_engine import Supertonic3Engine  # noqa: E402

ASSET_ROOT = ROOT / "install" / "assets" / "audio"
MANIFEST = ASSET_ROOT / "manifest.yaml"
ENGINES = (
    ("pockettts", PocketTTSEngine),
    ("supertonic3", Supertonic3Engine),
    ("moss_tts_nano", MossTtsNanoEngine),
)


def write_mp3(path: Path, audio, sample_rate: int) -> None:
    import lameenc
    import numpy as np

    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 1:
        channels = 1
    elif samples.ndim == 2 and samples.shape[1] in (1, 2):
        channels = samples.shape[1]
    else:
        raise ValueError(f"Unsupported synthesized audio shape: {samples.shape}")
    if samples.shape[0] < sample_rate // 4 or not np.isfinite(samples).all():
        raise ValueError(f"Invalid synthesized waveform: {samples.shape}")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(7)
    path.write_bytes(encoder.encode(pcm) + encoder.flush())


def update_manifest(entries: list[dict[str, str]]) -> None:
    import yaml

    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    samples = data.setdefault("samples", [])
    existing = {
        (row.get("stack_id"), row.get("model_id"), row.get("voice_id"))
        for row in samples
    }
    for entry in entries:
        key = (entry["stack_id"], entry["model_id"], entry["voice_id"])
        if key not in existing:
            samples.append(entry)
            existing.add(key)
    MANIFEST.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def generate(force: bool = False, model_ids: set[str] | None = None,
             voice_ids: set[str] | None = None) -> int:
    params = SpeakParams(volume=100)
    manifest_entries = []
    failures = 0
    for model_id, engine_type in ENGINES:
        if model_ids and model_id not in model_ids:
            continue
        engine = engine_type()
        for voice in engine.list_voices():
            if voice_ids and voice.id not in voice_ids:
                continue
            target = ASSET_ROOT / "ml" / model_id / f"{voice.id}.mp3"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file() and target.stat().st_size > 1_000 and not force:
                print(f"SKIP {model_id}/{voice.id}: existing {target.stat().st_size:,} bytes", flush=True)
            else:
                start = time.monotonic()
                print(f"SYNTH {model_id}/{voice.id}", flush=True)
                try:
                    result = engine.synthesize(SAMPLE_TEXT, voice.id, params)
                    if result is None:
                        raise RuntimeError("engine returned no audio")
                    audio, sample_rate = result
                    write_mp3(target, audio, int(sample_rate))
                    print(
                        f"OK {model_id}/{voice.id}: {target.stat().st_size:,} bytes "
                        f"in {time.monotonic() - start:.1f}s",
                        flush=True,
                    )
                except Exception as exc:
                    failures += 1
                    target.unlink(missing_ok=True)
                    print(f"FAILED {model_id}/{voice.id}: {type(exc).__name__}: {exc}", flush=True)
                    continue
            manifest_entries.append({
                "stack_id": "ml",
                "model_id": model_id,
                "voice_id": voice.id,
                "file": f"ml/{model_id}/{voice.id}.mp3",
            })
    update_manifest(manifest_entries)
    print(f"Finished: {len(manifest_entries)} samples registered; {failures} failures", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="regenerate existing previews")
    parser.add_argument("--model", action="append", choices=[item[0] for item in ENGINES],
                        help="limit generation to a model (may be repeated)")
    parser.add_argument("--voice", action="append", help="limit generation to a voice ID (may be repeated)")
    args = parser.parse_args()
    raise SystemExit(generate(args.force, set(args.model or []), set(args.voice or [])))
