"""Chatterbox 0.5B TTS engine (Resemble AI).

Auto-downloads from HuggingFace Hub on first use (ResembleAI/chatterbox).
Runs on CUDA when available, falls back to CPU.
No reference audio required — the default voice is built into model weights.

Install: pip install chatterbox-tts
"""
from __future__ import annotations

import threading

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from ..device import select_device
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("chatterbox")

_VOICES = [
    Voice(id="default",  name="Default"),
]
_DEFAULT_VOICE = "default"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)
_SAMPLE_RATE = 22_050
_HF_REPO = "ResembleAI/chatterbox"


class ChatterboxEngine(TtsEngine):
    """Chatterbox 0.5B — single class-level model singleton, daemon synth thread."""

    _model: object = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("ChatterboxEngine created — model will auto-download on first use")

    # ── Model singleton (shared across all instances) ─────────────────────────

    def _get_model(self):
        with ChatterboxEngine._model_lock:
            if ChatterboxEngine._model is None:
                from chatterbox.tts import ChatterboxTTS
                device = select_device()
                _log.info("loading Chatterbox from %s on device=%s", _HF_REPO, device)
                ChatterboxEngine._model = ChatterboxTTS.from_pretrained(device=device)
                _log.info("Chatterbox model ready")
            return ChatterboxEngine._model

    # ── TtsEngine API ─────────────────────────────────────────────────────────

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        if not text:
            return
        self.stop()
        self._stop_requested.clear()
        self._done.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id or _DEFAULT_VOICE, params),
            daemon=True,
            name="chatterbox-speak",
        ).start()

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1_000)

    # ── Internal ──────────────────────────────────────────────────────────────

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (audio_float32, sample_rate) without playing."""
        result = self._synthesize_array(text, voice_id or _DEFAULT_VOICE, params)
        return (result, _SAMPLE_RATE) if result is not None else None

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        if voice_id not in _VALID_VOICE_IDS:
            voice_id = _DEFAULT_VOICE
        model = self._get_model()
        _log.info("Chatterbox generating %d chars", len(text))
        wav = model.generate(text)
        audio = wav.squeeze().cpu().numpy().astype(np.float32)
        volume_scale = max(0.0, min(1.0, params.volume / 100.0))
        return audio * volume_scale

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            if self._stop_requested.is_set():
                return
            audio = self._synthesize_array(text, voice_id or _DEFAULT_VOICE, params)
            if audio is None or self._stop_requested.is_set():
                return
            play_audio(audio, _SAMPLE_RATE)
        except Exception as exc:
            _log.error("Chatterbox synthesis failed: %s", exc)
        finally:
            self._done.set()
