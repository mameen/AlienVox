"""Kyutai Pocket TTS engine.

Optional CPU-first engine. The dependency is imported lazily so a missing
``pocket-tts`` package cannot prevent AlienVox from starting.
"""
from __future__ import annotations

import threading

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from ..config import models_root
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("pockettts")
_SAMPLE_RATE = 24_000
_DEFAULT_VOICE = "alba"
_VOICES = [Voice(id="alba", name="Alba (English)"), Voice(id="marius", name="Marius (English)")]
_VALID_VOICES = frozenset(v.id for v in _VOICES)
_WEIGHTS_DIR = models_root() / "ml" / "pockettts"
_VOICE_PROMPTS = {
    "alba": _WEIGHTS_DIR / "voices" / "alba.safetensors",
    "marius": _WEIGHTS_DIR / "voices" / "marius.safetensors",
}


def resolve_voice(voice_id: str) -> str:
    return voice_id if voice_id in _VALID_VOICES else _DEFAULT_VOICE


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    return audio * max(0.0, min(1.0, volume / 100.0))


class PocketTTSEngine(TtsEngine):
    _model: object = None
    _voice_states: dict[str, object] = {}
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("PocketTTSEngine created; model loads lazily")

    @classmethod
    def _get_model(cls):
        with cls._lock:
            if cls._model is None:
                from pocket_tts import TTSModel  # type: ignore[import-untyped]
                config_path = _WEIGHTS_DIR / "english.yaml"
                if not config_path.is_file():
                    raise FileNotFoundError(
                        f"Pocket TTS weights are not installed under {_WEIGHTS_DIR}; "
                        "use Manage Voices to install them."
                    )
                cls._model = TTSModel.load_model(config=str(config_path))
            return cls._model

    def _get_voice_state(self, voice_id: str):
        voice_id = resolve_voice(voice_id)
        with self._lock:
            if voice_id not in self._voice_states:
                model = self._model
                if model is None:
                    from pocket_tts import TTSModel  # type: ignore[import-untyped]
                    config_path = _WEIGHTS_DIR / "english.yaml"
                    if not config_path.is_file():
                        raise FileNotFoundError(
                            f"Pocket TTS weights are not installed under {_WEIGHTS_DIR}; "
                            "use Manage Voices to install them."
                        )
                    model = TTSModel.load_model(config=str(config_path))
                    self._model = model
                self._voice_states[voice_id] = model.get_state_for_audio_prompt(
                    str(_VOICE_PROMPTS[voice_id])
                )
            return self._voice_states[voice_id]

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        if not text.strip():
            return
        self.stop()
        self._stop_requested.clear()
        self._done.clear()
        threading.Thread(target=self._do_speak, args=(text, voice_id, params), daemon=True,
                         name="pockettts-speak").start()

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1000)

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        model = self._get_model()
        audio = model.generate_audio(self._get_voice_state(voice_id), text)
        array = audio.detach().cpu().numpy().astype(np.float32)
        return apply_volume(array, params.volume), int(model.sample_rate or _SAMPLE_RATE)

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            result = self.synthesize(text, voice_id, params)
            if result and not self._stop_requested.is_set():
                play_audio(*result)
        except Exception as exc:
            _log.error("Pocket TTS synthesis failed: %s", exc)
        finally:
            self._done.set()
