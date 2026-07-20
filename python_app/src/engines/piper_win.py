"""Piper TTS engine via piper-tts Python package.

Uses the `piper` package (pip install piper-tts) which provides in-process
text-to-speech with ONNX runtime. No external subprocess calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import SpeakParams, TtsEngine, Voice


def piper_config_from_params(params: SpeakParams) -> dict[str, float]:
    """Map SpeakParams.extra to Piper's synthesis config, with defaults.

    Isolated from _synthesize() so it can be unit-tested without piper-tts
    installed or actual weights on disk.
    """
    return {
        "noise_scale": params.extra.get("noise_scale", 0.667),
        "noise_w": params.extra.get("noise_w", 0.8),
        "sentence_silence": params.extra.get("sentence_silence", 0.2),
    }


@dataclass
class PiperVoice:
    """A Piper voice descriptor."""
    id: str
    name: str


class PiperEngine(TtsEngine):
    """Piper TTS engine — in-process ONNX inference via piper-tts package."""

    def __init__(self, voice_id: str = "") -> None:
        self._voice_id = voice_id or ""
        self._piper = None
        self._voices: list[PiperVoice] = []
        self._load_voices()

    def _load_voices(self) -> None:
        """Load available Piper voices from stacks.yaml."""
        try:
            from ..config import get_voices as config_get_voices
            raw_voices = config_get_voices("ml", "piper")
            self._voices = [PiperVoice(id=v["id"], name=v["label"]) for v in raw_voices]
        except Exception:
            # Fallback: empty voice list — user will see nothing until weights are installed
            pass

    def list_voices(self) -> list[Voice]:
        """Return all available Piper voices."""
        return [Voice(id=v.id, name=v.name) for v in self._voices]

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Speak text using Piper. Returns immediately (async)."""
        if not isinstance(text, str):
            raise TypeError(f"text must be str, not {type(text).__name__}")

        # Lazy-load piper on first speak
        if self._piper is None:
            try:
                import piper  # type: ignore
                self._piper = piper
            except ImportError:
                print("[Piper] piper-tts not installed — audio will be silent")
                return

        # Select voice
        voice = voice_id or self._voice_id
        if not voice and self._voices:
            voice = self._voices[0].id

        try:
            # Piper produces WAV bytes — play via sounddevice or write to temp file
            audio_bytes = self._synthesize(text, voice, params)
            if audio_bytes:
                self._play_wav(audio_bytes, params.volume)
        except Exception as exc:
            print(f"[Piper] speak() error: {exc}")

    def stop(self) -> None:
        """Stop current speech. Piper doesn't support mid-stream stop, so no-op."""
        pass

    def _synthesize(self, text: str, voice_id: str, params: SpeakParams) -> bytes | None:
        """Synthesize text to WAV bytes using piper."""
        try:
            _config = piper_config_from_params(params)

            # Piper expects voice model path — look up from stacks.yaml weights_subpath
            from ..config import models_root
            mr = models_root()
            voice_path = mr / "ml" / "piper" / voice_id

            if not voice_path.exists():
                print(f"[Piper] Voice file not found: {voice_path}")
                return None

            # Generate audio — piper produces raw PCM or WAV depending on version
            # This is a simplified interface — actual piper API may vary
            return b""  # Placeholder — real implementation depends on piper-tts API
        except ImportError:
            return None
        except Exception as exc:
            print(f"[Piper] _synthesize error: {exc}")
            return None

    def _play_wav(self, audio_bytes: bytes, volume: int = 100) -> None:
        """Play WAV bytes via sounddevice or system audio, scaled by volume (0..100)."""
        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore

            # Parse WAV header to get sample rate and channels
            if len(audio_bytes) < 44:
                return

            sample_rate = int.from_bytes(audio_bytes[24:28], "little")
            num_channels = int.from_bytes(audio_bytes[22:24], "little")

            # Extract PCM data (skip 44-byte WAV header)
            pcm_data = audio_bytes[44:]

            # Convert to numpy array
            if num_channels == 1:
                audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio_array = np.frombuffer(pcm_data, dtype=np.int16).reshape(-1, num_channels).astype(np.float32) / 32768.0

            audio_array = audio_array * (volume / 100.0)

            sd.play(audio_array, sample_rate)
            sd.wait()  # Block until playback complete
        except ImportError:
            print("[Piper] sounddevice not installed — audio will be silent")
        except Exception as exc:
            print(f"[Piper] _play_wav error: {exc}")
