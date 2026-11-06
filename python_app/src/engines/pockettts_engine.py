"""Kyutai Pocket TTS engine.

Optional CPU-first engine. The dependency is imported lazily so a missing
``pocket-tts`` package cannot prevent AlienVox from starting. Each language
uses its own locally provisioned checkpoint; preset voice states are shared
across voices.
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
_VOICE_LANGUAGES = {
    "alba": "english", "marius": "english", "javert": "english",
    "cosette": "english", "jean": "english", "anna": "english",
    "vera": "english", "fantine": "english", "charles": "english",
    "paul": "english", "eponine": "english", "azelma": "english",
    "george": "english", "mary": "english", "jane": "english",
    "michael": "english", "eve": "english", "bill_boerst": "english",
    "peter_yearsley": "english", "stuart_bell": "english", "caro_davy": "english",
    "giovanni": "italian", "lola": "spanish", "juergen": "german",
    "rafael": "portuguese", "daan": "dutch", "estelle": "french",
}
_VOICE_NAMES = {
    "alba": "Alba", "marius": "Marius", "javert": "Javert",
    "cosette": "Cosette", "jean": "Jean", "anna": "Anna", "vera": "Vera",
    "fantine": "Fantine", "charles": "Charles", "paul": "Paul",
    "eponine": "Eponine", "azelma": "Azelma", "george": "George",
    "mary": "Mary", "jane": "Jane", "michael": "Michael", "eve": "Eve",
    "bill_boerst": "Bill Boerst", "peter_yearsley": "Peter Yearsley",
    "stuart_bell": "Stuart Bell", "caro_davy": "Caro Davy",
    "giovanni": "Giovanni", "lola": "Lola", "juergen": "Jürgen",
    "rafael": "Rafael", "daan": "Daan", "estelle": "Estelle",
}
_LANGUAGE_LABELS = {
    "english": "English", "italian": "Italian", "spanish": "Spanish",
    "german": "German", "portuguese": "Portuguese", "dutch": "Dutch",
    "french": "French",
}
_VOICE_NOTICES = {
    "cosette": " · Non-commercial license",
    "jean": " · Non-commercial license",
    "juergen": " · License unstated",
    "rafael": " · License unstated",
}
_VOICES = [
    Voice(
        id=voice_id,
        name=(f"{_VOICE_NAMES[voice_id]} ({_LANGUAGE_LABELS[language]}"
              f"{_VOICE_NOTICES.get(voice_id, '')})"),
    )
    for voice_id, language in _VOICE_LANGUAGES.items()
]
_VALID_VOICES = frozenset(_VOICE_LANGUAGES)
_WEIGHTS_DIR = models_root() / "ml" / "pockettts"


def resolve_voice(voice_id: str) -> str:
    return voice_id if voice_id in _VALID_VOICES else _DEFAULT_VOICE


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    return audio * max(0.0, min(1.0, volume / 100.0))


class PocketTTSEngine(TtsEngine):
    _models: dict[str, object] = {}
    _voice_states: dict[str, object] = {}
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("PocketTTSEngine created; model loads lazily")

    @classmethod
    def _get_model(cls, language: str):
        with cls._lock:
            if language not in cls._models:
                from pocket_tts import TTSModel  # type: ignore[import-untyped]
                config_path = _WEIGHTS_DIR / f"{language}.yaml"
                if not config_path.is_file():
                    raise FileNotFoundError(
                        f"Pocket TTS {language} weights are not installed under {_WEIGHTS_DIR}; "
                        "use Manage Voices to install them."
                    )
                cls._models[language] = TTSModel.load_model(config=str(config_path))
            return cls._models[language]

    @classmethod
    def _get_voice_state(cls, voice_id: str):
        voice_id = resolve_voice(voice_id)
        with cls._lock:
            if voice_id not in cls._voice_states:
                language = _VOICE_LANGUAGES[voice_id]
                model = cls._models.get(language)
                if model is None:
                    from pocket_tts import TTSModel  # type: ignore[import-untyped]
                    config_path = _WEIGHTS_DIR / f"{language}.yaml"
                    if not config_path.is_file():
                        raise FileNotFoundError(
                            f"Pocket TTS {language} weights are not installed under {_WEIGHTS_DIR}; "
                            "use Manage Voices to install them."
                        )
                    model = TTSModel.load_model(config=str(config_path))
                    cls._models[language] = model
                prompt_path = _WEIGHTS_DIR / "voices" / f"{voice_id}.safetensors"
                if not prompt_path.is_file():
                    raise FileNotFoundError(
                        f"Pocket TTS preset voice '{voice_id}' is missing at {prompt_path}; "
                        "use Manage Voices to install it."
                    )
                cls._voice_states[voice_id] = model.get_state_for_audio_prompt(str(prompt_path))
            return cls._voice_states[voice_id]

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
        voice_id = resolve_voice(voice_id)
        language = _VOICE_LANGUAGES[voice_id]
        model = self._get_model(language)
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
