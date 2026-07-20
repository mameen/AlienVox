"""Dia 1.6B dialogue TTS engine (nari-labs).

Auto-downloads from HuggingFace Hub on first use (nari-labs/Dia-1.6B).
Models runs in float16 — requires ~3.5 GB VRAM, runs comfortably on a 4090.

Voice IDs map to Dia's speaker tokens:
  s1  →  [S1]  (first speaker)
  s2  →  [S2]  (second speaker)

For single-speaker use, the text is wrapped in the chosen speaker tag
automatically. Multi-turn dialogue must be pre-tagged by the caller.

Install: pip install git+https://github.com/nari-labs/dia.git
"""
from __future__ import annotations

import threading

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("dia")

_VOICES = [
    Voice(id="s1", name="[S1] Speaker 1"),
    Voice(id="s2", name="[S2] Speaker 2"),
]
_DEFAULT_VOICE = "s1"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)
_SAMPLE_RATE = 44_100
_HF_REPO = "nari-labs/Dia-1.6B"
_TAG: dict[str, str] = {"s1": "[S1]", "s2": "[S2]"}


class DiaEngine(TtsEngine):
    """Dia 1.6B — single class-level model singleton, daemon synth thread."""

    _model: object = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("DiaEngine created — model will auto-download on first use (~3.5 GB)")

    # ── Model singleton ───────────────────────────────────────────────────────

    def _get_model(self):
        with DiaEngine._model_lock:
            if DiaEngine._model is None:
                _log.info("loading Dia 1.6B from %s (float16)", _HF_REPO)
                from dia.model import Dia
                DiaEngine._model = Dia.from_pretrained(_HF_REPO, compute_dtype="float16")
                _log.info("Dia model ready")
            return DiaEngine._model

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
            name="dia-speak",
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
        tag = _TAG.get(voice_id, "[S1]")
        tagged = text.strip() if ("[S1]" in text or "[S2]" in text) else f"{tag} {text.strip()}"
        model = self._get_model()
        _log.info("Dia generating %d chars (speaker=%s)", len(text), voice_id)
        output = model.generate(tagged, verbose=False)
        audio = np.asarray(output, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=0)
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
            _log.error("Dia synthesis failed: %s", exc)
        finally:
            self._done.set()
