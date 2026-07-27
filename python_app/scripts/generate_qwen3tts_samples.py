"""Generate offline MP3 samples for all Qwen3TTS voices.

Usage:
    cd python_app
    .venv\\Scripts\\python.exe scripts/generate_qwen3tts_samples.py

Outputs to install/assets/audio/ml/qwen3tts/ (dev + prod shared).
Also updates install/assets/audio/manifest.yaml with the new entries.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"C:\dev\personal\.repos\tts\python_app")
SAMPLES_DIR = ROOT / "install" / "assets" / "audio" / "ml" / "qwen3tts"
MANIFEST = ROOT / "install" / "assets" / "audio" / "manifest.yaml"

# Same text used by all other ML engines for consistent comparison.
# This is the canonical sample phrase — defined in app_controller.py as SAMPLE_TEXT.
# All offline voice samples across the product use this exact phrase.
SAMPLE_TEXT = (
    "Welcome to AlienVox. This is a performance test of your TTS engine. "
    "If you can hear this, your system is working correctly."
)

_VOICES = [
    ("vivian",   "Vivian (F · ZH/EN)"),
    ("serena",   "Serena (F · ZH/EN)"),
    ("dylan",    "Dylan (M · EN)"),
    ("eric",     "Eric (M · EN)"),
    ("ryan",     "Ryan (M · EN)"),
    ("aiden",    "Aiden (M · EN)"),
    ("uncle_fu", "Uncle Fu (M · ZH)"),
    ("ono_anna", "Ono Anna (F · JA)"),
    ("sohee",    "Sohee (F · KO)"),
]


def generate_samples():
    """Generate MP3 samples for all Qwen3TTS voices."""
    print(f"Generating Qwen3TTS samples → {SAMPLES_DIR}")
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    from src.engines.qwen3tts_engine import Qwen3TTSEngine
    from src.engines.base import SpeakParams

    engine = Qwen3TTSEngine()

    for voice_id, label in _VOICES:
        mp3_path = SAMPLES_DIR / f"{voice_id}.mp3"
        print(f"\n  [{voice_id}] {label} ...", end=" ", flush=True)

        try:
            result = engine.synthesize(SAMPLE_TEXT, voice_id, SpeakParams(volume=100))
            if result is None:
                print("SKIPPED (synthesize returned None)")
                continue

            audio, sr = result
            import numpy as np
            # Convert float32 [-1, 1] to int16 WAV first, then encode to MP3
            audio_int16 = (audio * 32767).astype(np.int16)
            import soundfile as sf
            import lameenc
            
            # Write temp WAV, then encode to MP3
            tmp_wav = mp3_path.with_suffix(".wav")
            sf.write(str(tmp_wav), audio_int16, sr)
            
            encoder = lameenc.Encoder()
            encoder.set_bit_rate(128)
            encoder.set_in_sample_rate(sr)
            encoder.set_channels(1)
            encoder.set_quality(7)  # best quality
            
            wav_bytes = tmp_wav.read_bytes()
            mp3_bytes = encoder.encode(wav_bytes)
            mp3_bytes += encoder.flush()
            
            mp3_path.write_bytes(mp3_bytes)
            tmp_wav.unlink(missing_ok=True)

            size_kb = mp3_path.stat().st_size / 1024
            duration_s = len(audio) / sr if sr > 0 else 0
            print(f"OK — {size_kb:.0f} KB, {duration_s:.1f}s @ {sr}Hz")

        except Exception as exc:
            print(f"FAILED — {exc}")


def update_manifest():
    """Add qwen3tts entries to manifest.yaml."""
    import yaml

    if MANIFEST.exists():
        data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}
    else:
        data = {"samples": []}

    samples = data.get("samples", [])

    # Check if qwen3tts entries already exist
    existing_qwen = [s for s in samples if s.get("model_id") == "qwen3tts"]
    if existing_qwen:
        print(f"\n  manifest.yaml already has {len(existing_qwen)} qwen3tts entries — skipping update.")
        return

    # Add new entries (after the last ml entry)
    insert_idx = len(samples)
    for voice_id, _ in _VOICES:
        samples.insert(insert_idx, {
            "stack_id": "ml",
            "model_id": "qwen3tts",
            "voice_id": voice_id,
            "file": f"ml/qwen3tts/{voice_id}.mp3",
        })
        insert_idx += 1

    data["samples"] = samples
    MANIFEST.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    print(f"\n  Updated manifest.yaml with {len(_VOICES)} qwen3tts entries.")


if __name__ == "__main__":
    generate_samples()
    update_manifest()
    print("\nDone!")
