"""Supertonic 3 local ONNX TTS adapter."""
from __future__ import annotations

import threading

import numpy as np

from ..audio_player import play_audio, stop_playback
from ..config import models_root
from .base import SpeakParams, TtsEngine, Voice

_VOICES = [Voice(id=v, name=v) for v in ("M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5")]
_DEFAULT_VOICE = "M1"
_MODEL_DIR = models_root() / "ml" / "supertonic3"


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32) * max(0.0, min(1.0, volume / 100.0))


class Supertonic3Engine(TtsEngine):
    _tts = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()

    @classmethod
    def _get_tts(cls):
        with cls._lock:
            if cls._tts is None:
                from supertonic import TTS
                cls._tts = TTS(model="supertonic-3", model_dir=_MODEL_DIR, auto_download=False)
            return cls._tts

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        tts = self._get_tts()
        voice = voice_id if voice_id in {v.id for v in _VOICES} else _DEFAULT_VOICE
        style = tts.get_voice_style(voice_name=voice)
        wav, _duration = tts.synthesize(text, lang=params.extra.get("lang", "en"), voice_style=style)
        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        return apply_volume(audio, params.volume), int(tts.sample_rate)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        self.stop()
        self._stop_requested.clear()
        self._done.clear()
        threading.Thread(target=self._do_speak, args=(text, voice_id, params), daemon=True).start()

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
            _logger.get_logger("supertonic3").exception("Supertonic 3 synthesis failed")
        finally:
            self._done.set()
