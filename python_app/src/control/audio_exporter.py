"""Audio export — WAV and MP3, no CLI tools required.

Workflow:
  1. Engine synthesises audio → numpy float32 array  (or SAPI → native WAV)
  2. Intermediate saved to  .generated/<session>-<ts>.<ext>
  3. Final file written to caller-chosen destination path

MP3 encoding uses lameenc (bundled libmp3lame wheel, MIT-compatible, no exe).
WAV writing uses soundfile (libsndfile, BSD, already a dependency).

For SAPI engines that cannot produce a numpy array, the caller must use
engine.speak_to_wav() directly and pass the resulting WAV through
convert_wav_to_mp3() if MP3 is needed.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .engines.base import SpeakParams, TtsEngine

# Intermediate files land here (gitignored)
_GENERATED_DIR = Path(__file__).parent.parent.parent / ".generated"


def generated_dir() -> Path:
    _GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    return _GENERATED_DIR


def intermediate_path(suffix: str = ".wav") -> Path:
    ts = time.time_ns() // 1_000_000
    return generated_dir() / f"alienvox-{ts}{suffix}"


# ── WAV ───────────────────────────────────────────────────────────────────────

def write_wav(audio: np.ndarray, sample_rate: int, dest: Path) -> None:
    """Write float32 audio to a WAV file via soundfile (already a dependency)."""
    import soundfile as sf
    dest.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dest), audio, sample_rate, subtype="PCM_16")


# ── MP3 ───────────────────────────────────────────────────────────────────────

def _encode_mp3(audio: np.ndarray, sample_rate: int, bitrate: int = 192) -> bytes:
    """Encode float32 mono/stereo numpy array to MP3 bytes using lameenc."""
    try:
        import lameenc
    except ImportError as exc:
        raise RuntimeError(
            "lameenc is not installed — run: pip install lameenc"
        ) from exc

    # lameenc expects int16 PCM
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)

    channels = 1 if pcm.ndim == 1 else pcm.shape[0]
    if pcm.ndim > 1:
        pcm = pcm.T.flatten()  # interleaved stereo

    enc = lameenc.Encoder()
    enc.set_bit_rate(bitrate)
    enc.set_in_sample_rate(sample_rate)
    enc.set_channels(channels)
    enc.set_quality(2)  # 2 = near-best, 7 = fastest
    enc.silence()       # suppress LAME banner on stderr

    data = enc.encode(pcm.tobytes())
    data += enc.flush()
    return data


def write_mp3(audio: np.ndarray, sample_rate: int, dest: Path, bitrate: int = 192) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_encode_mp3(audio, sample_rate, bitrate))


def convert_wav_to_mp3(wav_path: Path, dest: Path, bitrate: int = 192) -> None:
    """Convert an existing WAV file to MP3 (used for SAPI export)."""
    import soundfile as sf
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    write_mp3(audio, sr, dest, bitrate)


# ── High-level export ─────────────────────────────────────────────────────────

class ExportError(Exception):
    pass


def export_audio(
    engine: "TtsEngine",
    text: str,
    voice_id: str,
    params: "SpeakParams",
    dest: Path,
    *,
    on_progress: "callable[[str], None] | None" = None,
) -> None:
    """Synthesise text and write to dest (WAV or MP3 based on suffix).

    on_progress(msg) is called with status strings so the UI can update a
    progress label.  Raises ExportError on failure.
    """
    fmt = dest.suffix.lower()
    if fmt not in (".wav", ".mp3"):
        raise ExportError(f"Unsupported export format: {fmt!r} (use .wav or .mp3)")

    def _prog(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _prog("Synthesising audio…")

    # Try synthesize() first (ML engines)
    result = engine.synthesize(text, voice_id, params)

    if result is not None:
        audio, sr = result
        inter = intermediate_path(".wav")
        _prog("Writing intermediate WAV…")
        write_wav(audio, sr, inter)

        if fmt == ".wav":
            _prog("Copying to destination…")
            import shutil
            shutil.copy2(inter, dest)
        else:
            _prog("Encoding MP3…")
            write_mp3(audio, sr, dest)

        _prog("Done.")
        return

    # Fallback: SAPI speak_to_wav
    speak_to_wav = getattr(engine, "speak_to_wav", None)
    if speak_to_wav is None:
        raise ExportError(
            "This engine does not support audio export. "
            "Use an ML engine (Kokoro, Chatterbox, Dia, F5-TTS, OuteTTS) for WAV/MP3 export."
        )

    from .engines.base import SpeakParams as _SP
    inter = intermediate_path(".wav")
    _prog("Generating WAV via SAPI…")
    done = speak_to_wav(text, voice_id, params, inter)
    # speak_to_wav returns an Event or similar — wait for it
    if hasattr(done, "wait"):
        done.wait(timeout=120)

    if not inter.exists() or inter.stat().st_size == 0:
        raise ExportError("SAPI WAV export produced no output.")

    if fmt == ".wav":
        _prog("Copying to destination…")
        import shutil
        shutil.copy2(inter, dest)
    else:
        _prog("Encoding MP3…")
        convert_wav_to_mp3(inter, dest)

    _prog("Done.")
