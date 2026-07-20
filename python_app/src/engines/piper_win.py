"""Piper TTS engine via piper-tts Python package.

Uses the `piper` package (pip install piper-tts) which provides in-process
ONNX inference via PiperVoice.load()/synthesize(). No external subprocess
calls — matches the AlienVox constraint that all inference happens in this
process (the Rust prototype shelled out to `python -m piper` per-utterance;
this port keeps the model loaded and runs entirely in-process instead).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("piper")


def piper_config_from_params(params: SpeakParams) -> dict[str, float]:
    """Map SpeakParams.extra to Piper's synthesis config, with defaults.

    Isolated from _synthesize_array() so it can be unit-tested without
    piper-tts installed or actual weights on disk.
    """
    return {
        "noise_scale": params.extra.get("noise_scale", 0.667),
        "noise_w": params.extra.get("noise_w", 0.8),
        "sentence_silence": params.extra.get("sentence_silence", 0.2),
    }


def rate_to_length_scale(rate: int) -> float:
    """Convert SAPI-style rate (-10..+10) to Piper's length_scale (>1 = slower).

    Mirrors the mapping used by the Rust implementation's piper_tts.py runner.
    """
    clamped = max(-10, min(10, rate))
    return max(0.5, min(2.0, 1.0 - (clamped / 30.0)))


def find_voice_model(models_root: Path, voice_id: str) -> tuple[Path, Path] | None:
    """Locate a Piper voice's .onnx model + .onnx.json config under models_root.

    Voice files live nested by language/name/quality (e.g.
    ml/piper/en/en_US/lessac/medium/en_US-lessac-medium.onnx) — searched
    recursively since the exact subpath isn't recorded in stacks.yaml.
    """
    piper_dir = models_root / "ml" / "piper"
    if not piper_dir.exists():
        return None
    matches = list(piper_dir.rglob(f"{voice_id}.onnx"))
    if not matches:
        return None
    model_path = matches[0]
    config_path = model_path.with_suffix(".onnx.json")
    return (model_path, config_path) if config_path.exists() else None


@dataclass
class PiperVoiceEntry:
    """A Piper voice descriptor (catalog metadata, not the loaded model)."""
    id: str
    name: str


class PiperEngine(TtsEngine):
    """Piper TTS engine — in-process ONNX inference via piper-tts package."""

    def __init__(self, voice_id: str = "") -> None:
        self._voice_id = voice_id or ""
        self._voices: list[PiperVoiceEntry] = []
        self._loaded_voices: dict[str, object] = {}  # voice_id -> piper.PiperVoice
        self._load_lock = threading.Lock()
        self._done = threading.Event()
        self._stop_requested = threading.Event()
        self._load_voices()

    def _load_voices(self) -> None:
        """Load available Piper voices from stacks.yaml."""
        try:
            from ..config import get_voices as config_get_voices
            raw_voices = config_get_voices("ml", "piper")
            self._voices = [PiperVoiceEntry(id=v["id"], name=v["label"]) for v in raw_voices]
        except Exception:
            # Fallback: empty voice list — user will see nothing until weights are installed
            pass

    def list_voices(self) -> list[Voice]:
        """Return all available Piper voices."""
        return [Voice(id=v.id, name=v.name) for v in self._voices]

    def _get_voice_model(self, voice_id: str):
        """Load (and cache) a piper.PiperVoice for the given voice_id."""
        with self._load_lock:
            if voice_id in self._loaded_voices:
                return self._loaded_voices[voice_id]

            from ..config import models_root
            from piper import PiperVoice as _PiperModel

            paths = find_voice_model(models_root(), voice_id)
            if paths is None:
                _log.error("voice model not found for %r under .models/ml/piper", voice_id)
                return None

            model_path, config_path = paths
            _log.info("loading Piper voice %s from %s", voice_id, model_path)
            voice = _PiperModel.load(str(model_path), config_path=str(config_path))
            self._loaded_voices[voice_id] = voice
            return voice

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Speak text using Piper. Returns immediately (async)."""
        if not isinstance(text, str):
            raise TypeError(f"text must be str, not {type(text).__name__}")
        if not text:
            return

        self._done.clear()
        self._stop_requested.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id or self._voice_id, params),
            daemon=True,
            name="piper-speak",
        ).start()

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (audio_float32, sample_rate) without playing."""
        return self._synthesize_array(text, voice_id or self._voice_id, params)

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        if not text:
            return None

        voice = self._get_voice_model(voice_id)
        if voice is None:
            return None

        from piper import SynthesisConfig

        cfg = piper_config_from_params(params)
        syn_config = SynthesisConfig(
            length_scale=rate_to_length_scale(params.rate),
            noise_scale=max(0.0, min(1.0, cfg["noise_scale"])),
            noise_w_scale=max(0.0, min(1.0, cfg["noise_w"])),
            volume=1.0,  # applied by our own volume scaling below, not piper's
        )
        sentence_silence_s = max(0.0, min(5.0, cfg["sentence_silence"]))

        chunks: list[np.ndarray] = []
        sample_rate = 22_050
        try:
            for i, audio_chunk in enumerate(voice.synthesize(text, syn_config)):
                if self._stop_requested.is_set():
                    return None
                sample_rate = audio_chunk.sample_rate
                if i > 0 and sentence_silence_s > 0:
                    silence = np.zeros(int(sentence_silence_s * sample_rate), dtype=np.float32)
                    chunks.append(silence)
                chunks.append(audio_chunk.audio_float_array.astype(np.float32))
        except Exception as exc:
            _log.error("Piper synthesis failed: %s", exc)
            return None

        if not chunks:
            return None

        audio = np.concatenate(chunks) * (params.volume / 100.0)
        return audio.astype(np.float32), sample_rate

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            result = self._synthesize_array(text, voice_id, params)
            if result is None or self._stop_requested.is_set():
                return
            audio, sample_rate = result
            _log.trace("synthesis complete — %d samples @ %d Hz", len(audio), sample_rate)
            play_audio(audio, sample_rate)
            _log.trace("playback complete")
        except Exception as exc:
            _log.error("piper speak failed: %s", exc)
        finally:
            self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1000.0)

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def pause(self) -> None:
        stop_playback()

    def resume(self) -> None:
        pass  # not supported for streaming ML engine
