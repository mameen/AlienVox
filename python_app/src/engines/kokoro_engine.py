"""Kokoro-82M TTS engine.

Auto-downloads model weights from HuggingFace Hub on first use via
KPipeline(repo_id='hexgrad/Kokoro-82M'). No manual download step required.

Voice IDs match stacks.yaml ml/kokoro voices (af_heart, af_bella, etc.).
"""
from __future__ import annotations

import threading

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("kokoro")

_VOICES = [
    Voice(id="af_heart",   name="American F · Heart"),
    Voice(id="af_bella",   name="American F · Bella"),
    Voice(id="af_nicole",  name="American F · Nicole"),
    Voice(id="am_adam",    name="American M · Adam"),
    Voice(id="am_michael", name="American M · Michael"),
    Voice(id="bf_emma",    name="British F · Emma"),
    Voice(id="bm_george",  name="British M · George"),
]

_SAMPLE_RATE = 24_000
_DEFAULT_VOICE = "af_heart"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)

# lang_code per voice prefix: 'a' = American English, 'b' = British English
_LANG_MAP = {
    "a": "a",  # American
    "b": "b",  # British
}


def _lang_for_voice(voice_id: str) -> str:
    prefix = voice_id[0] if voice_id else "a"
    return _LANG_MAP.get(prefix, "a")


class KokoroEngine(TtsEngine):
    """Kokoro-82M ML TTS engine backed by a single pipeline worker thread."""

    def __init__(self) -> None:
        self._pipeline_lock = threading.Lock()
        self._pipelines: dict[str, object] = {}  # lang_code -> KPipeline
        self._done = threading.Event()
        self._playing = threading.Event()
        self._stop_requested = threading.Event()
        _log.info("KokoroEngine created — model will auto-download on first use")

    def _get_pipeline(self, lang_code: str):
        with self._pipeline_lock:
            if lang_code not in self._pipelines:
                _log.info("loading KPipeline lang=%s (may download weights)", lang_code)
                from kokoro import KPipeline
                pipe = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
                self._pipelines[lang_code] = pipe
                _log.info("KPipeline lang=%s ready", lang_code)
            return self._pipelines[lang_code]

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        if not text:
            return
        self._done.clear()
        self._stop_requested.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id or _DEFAULT_VOICE, params),
            daemon=True,
            name="kokoro-speak",
        ).start()

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            if voice_id not in _VALID_VOICE_IDS:
                _log.warn("voice_id=%r is not a Kokoro voice — falling back to %s", voice_id, _DEFAULT_VOICE)
                voice_id = _DEFAULT_VOICE
            lang_code = _lang_for_voice(voice_id)
            pipe = self._get_pipeline(lang_code)

            speed = _rate_to_speed(params.rate)
            volume = params.volume / 100.0

            _log.trace("generating voice=%s speed=%.2f", voice_id, speed)

            chunks: list[np.ndarray] = []
            for _gs, _ps, audio in pipe(text=text, voice=voice_id, speed=speed):
                if self._stop_requested.is_set():
                    _log.trace("stop requested — aborting generation")
                    return
                if audio is not None and len(audio) > 0:
                    arr = np.array(audio, dtype=np.float32) * volume
                    chunks.append(arr)

            if not chunks or self._stop_requested.is_set():
                return

            audio_out = np.concatenate(chunks)
            _log.trace("synthesis complete — %d samples @ %d Hz", len(audio_out), _SAMPLE_RATE)

            play_audio(audio_out, _SAMPLE_RATE)
            _log.trace("playback complete")
        except Exception as exc:
            _log.error("kokoro speak failed: %s", exc)
        finally:
            self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1000.0)

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def pause(self) -> None:
        # sounddevice doesn't support pause/resume natively; stop instead
        stop_playback()

    def resume(self) -> None:
        pass  # not supported for streaming ML engine


def _rate_to_speed(rate: int) -> float:
    """Convert SAPI-style rate (-10..+10) to Kokoro speed multiplier (0.5..2.0)."""
    clamped = max(-10, min(10, rate))
    if clamped >= 0:
        return 1.0 + clamped * 0.1   # 1.0 .. 2.0
    return 1.0 + clamped * 0.05      # 0.5 .. 1.0
