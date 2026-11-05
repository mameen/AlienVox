"""MOSS-TTS-Nano official ONNX CPU runtime adapter."""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

import numpy as np

from ..audio_player import play_audio, stop_playback
from ..config import models_root
from .base import SpeakParams, TtsEngine, Voice

_VOICE_IDS = (
    "Junhao", "Zhiming", "Weiguo", "Xiaoyu", "Yuewen", "Lingyu", "Trump",
    "Ava", "Bella", "Adam", "Nathan", "Soyo", "Saki", "Mortis", "Umiri",
    "Mei", "Anon", "Arisa",
)
_VOICES = [Voice(id=voice, name=voice) for voice in _VOICE_IDS]
_MODEL_DIR = models_root() / "ml" / "moss_tts_nano"


def resolve_voice(voice_id: str | None) -> str:
    return voice_id if voice_id in _VOICE_IDS else "Ava"


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    scale = max(0.0, min(1.0, volume / 100.0))
    return np.asarray(audio, dtype=np.float32) * scale


def validate_waveform(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Reject malformed runtime output before it is reported as successful audio."""
    waveform = np.asarray(audio, dtype=np.float32)
    if sample_rate <= 0:
        raise ValueError(f"MOSS returned invalid sample rate: {sample_rate}")
    if waveform.ndim != 2 or waveform.shape[1] != 2:
        raise ValueError(f"MOSS must return stereo audio; got shape {waveform.shape}")
    if waveform.shape[0] < sample_rate // 4:
        raise ValueError(
            f"MOSS returned only {waveform.shape[0]} samples at {sample_rate} Hz"
        )
    if not np.isfinite(waveform).all():
        raise ValueError("MOSS returned non-finite audio samples")
    return waveform


class MossTtsNanoEngine(TtsEngine):
    _runtime = None
    _runtime_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()

    @classmethod
    def _get_runtime(cls):
        with cls._runtime_lock:
            if cls._runtime is None:
                from onnx_tts_runtime import OnnxTtsRuntime

                cls._runtime = OnnxTtsRuntime(
                    model_dir=_MODEL_DIR,
                    output_dir=Path(tempfile.gettempdir()) / "alienvox-moss-runtime",
                    thread_count=max(1, min(4, os.cpu_count() or 1)),
                    execution_provider="cpu",
                )
            return cls._runtime

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        runtime = self._get_runtime()
        with self._runtime_lock:
            with tempfile.TemporaryDirectory(prefix="alienvox-moss-") as temp_dir:
                result = runtime.synthesize(
                    text=text,
                    voice=resolve_voice(voice_id),
                    output_audio_path=Path(temp_dir) / "synthesis.wav",
                    sample_mode="greedy",
                    do_sample=False,
                    streaming=False,
                    enable_wetext=False,
                    enable_normalize_tts_text=False,
                )
        sample_rate = int(result["sample_rate"])
        waveform = validate_waveform(result["waveform"], sample_rate)
        audio = apply_volume(waveform, params.volume)
        return audio, sample_rate

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        if not text.strip():
            return
        self.stop()
        self._stop_requested.clear()
        self._done.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id, params),
            daemon=True,
            name="moss-tts-nano-speak",
        ).start()

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout_ms / 1000)

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            result = self.synthesize(text, voice_id, params)
            if result and not self._stop_requested.is_set():
                play_audio(*result)
        except Exception:
            from .. import logger as _logger
            _logger.get_logger("moss_tts_nano").exception("MOSS-TTS-Nano synthesis failed")
        finally:
            self._done.set()
