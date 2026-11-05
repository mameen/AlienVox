"""Supertonic 3 ONNX TTS adapter, configured for local CPU inference."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..base import SpeakParams, TtsEngine, Voice

VOICES = [Voice(code, f"{'Female' if code.startswith('F') else 'Male'} {code[1:]}") for code in ("F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5")]


def models_root() -> Path:
    override = os.environ.get("ALIENVOX_MODELS_DIR")
    if override:
        return Path(override).expanduser()
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "com.alientech.alienvox" / ".models"


class Supertonic3Engine(TtsEngine):
    _tts = None

    def __init__(self, device: str = "cpu") -> None:
        if device not in ("cpu", "cuda", "gpu"):
            raise ValueError(f"unsupported Supertonic device: {device}")

    @classmethod
    def _get_tts(cls):
        if cls._tts is None:
            model_dir = models_root() / "ml" / "supertonic3"
            if not model_dir.is_dir():
                raise FileNotFoundError(f"Supertonic 3 model directory not found: {model_dir}")
            from supertonic import TTS
            cls._tts = TTS(model="supertonic-3", model_dir=model_dir, auto_download=False)
        return cls._tts

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        if voice_id not in {voice.id for voice in VOICES}:
            raise ValueError(f"unknown Supertonic voice {voice_id!r}; use list_voices(engine='supertonic3')")
        tts = self._get_tts()
        style = tts.get_voice_style(voice_name=voice_id)
        wav, _ = tts.synthesize(text, lang=params.extra.get("lang", "en"), voice_style=style)
        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        audio *= max(0, min(100, params.volume)) / 100.0
        return audio, int(tts.sample_rate)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        raise RuntimeError("Supertonic3Engine.speak is not used by MCP; synthesize audio and play it via the MCP tool")

    def stop(self) -> None:
        pass
