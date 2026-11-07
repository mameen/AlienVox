"""Piper CPU TTS adapter using locally installed voice files."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from ..base import SpeakParams, TtsEngine, Voice

VOICES = [
    Voice("en_US-ryan-high", "Ryan (US English, high quality)"),
    Voice("en_US-kathleen-low", "Kathleen (US English, low resource)"),
    Voice("en_GB-southern_english_female-low", "Southern English Female (UK, low resource)"),
    Voice("en_US-lessac-medium", "Lessac (US English, medium)"),
    Voice("en_US-amy-medium", "Amy (US English, medium)"),
    Voice("en_GB-jenny_dioco-medium", "Jenny Dioco (UK English, medium)"),
    Voice("en_GB-alan-medium", "Alan (UK English, medium)"),
]


def models_root() -> Path:
    override = os.environ.get("ALIENVOX_MODELS_DIR")
    if override:
        return Path(override).expanduser()
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local / "com.alientech.alienvox" / ".models"


class PiperEngine(TtsEngine):
    def __init__(self, device: str = "cpu") -> None:
        if device not in ("cpu", "cuda", "gpu"):
            raise ValueError(f"unsupported Piper device: {device}")
        self._models: dict[str, object] = {}

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def _load(self, voice_id: str):
        if voice_id not in {voice.id for voice in VOICES}:
            raise ValueError(f"unknown Piper voice {voice_id!r}; use list_voices(engine='piper')")
        if voice_id not in self._models:
            root = models_root() / "ml" / "piper"
            matches = list(root.rglob(f"{voice_id}.onnx")) if root.exists() else []
            if not matches:
                raise FileNotFoundError(f"Piper model {voice_id!r} not installed under {root}")
            model = matches[0]
            config = model.with_suffix(".onnx.json")
            if not config.is_file():
                raise FileNotFoundError(f"Piper model config missing: {config}")
            from piper import PiperVoice
            self._models[voice_id] = PiperVoice.load(str(model), config_path=str(config))
        return self._models[voice_id]

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        from piper import SynthesisConfig
        cfg = SynthesisConfig(volume=1.0, length_scale=max(0.5, min(2.0, 1.0 - max(-10, min(10, params.rate)) / 30.0)))
        chunks = [chunk for chunk in self._load(voice_id).synthesize(text, cfg)]
        if not chunks:
            raise RuntimeError("Piper returned no audio")
        rate = chunks[0].sample_rate
        silence = np.zeros(int(0.2 * rate), dtype=np.float32)
        audio_parts = []
        for index, chunk in enumerate(chunks):
            if index:
                audio_parts.append(silence)
            audio_parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
        audio = np.concatenate(audio_parts) * (max(0, min(100, params.volume)) / 100.0)
        return audio.astype(np.float32), int(rate)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        raise RuntimeError("PiperEngine.speak is not used by MCP; synthesize audio and play it via the MCP tool")

    def stop(self) -> None:
        pass
