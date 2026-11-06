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

_VOICE_LABELS = {
    "af_alloy": "American F · Alloy", "af_aoede": "American F · Aoede",
    "af_bella": "American F · Bella", "af_heart": "American F · Heart",
    "af_jessica": "American F · Jessica", "af_kore": "American F · Kore",
    "af_nicole": "American F · Nicole", "af_nova": "American F · Nova",
    "af_river": "American F · River", "af_sarah": "American F · Sarah",
    "af_sky": "American F · Sky", "am_adam": "American M · Adam",
    "am_echo": "American M · Echo", "am_eric": "American M · Eric",
    "am_fenrir": "American M · Fenrir", "am_liam": "American M · Liam",
    "am_michael": "American M · Michael", "am_onyx": "American M · Onyx",
    "am_puck": "American M · Puck", "am_santa": "American M · Santa",
    "bf_alice": "British F · Alice", "bf_emma": "British F · Emma",
    "bf_isabella": "British F · Isabella", "bf_lily": "British F · Lily",
    "bm_daniel": "British M · Daniel", "bm_fable": "British M · Fable",
    "bm_george": "British M · George", "bm_lewis": "British M · Lewis",
    "ef_dora": "Spanish F · Dora", "em_alex": "Spanish M · Alex",
    "em_santa": "Spanish M · Santa", "ff_siwis": "French F · Siwis",
    "hf_alpha": "Hindi F · Alpha", "hf_beta": "Hindi F · Beta",
    "hm_omega": "Hindi M · Omega", "hm_psi": "Hindi M · Psi",
    "if_sara": "Italian F · Sara", "im_nicola": "Italian M · Nicola",
    "jf_alpha": "Japanese F · Alpha", "jf_gongitsune": "Japanese F · Gongitsune",
    "jf_nezumi": "Japanese F · Nezumi", "jf_tebukuro": "Japanese F · Tebukuro",
    "jm_kumo": "Japanese M · Kumo", "pf_dora": "Portuguese F · Dora",
    "pm_alex": "Portuguese M · Alex", "pm_santa": "Portuguese M · Santa",
    "zf_xiaobei": "Chinese F · Xiaobei", "zf_xiaoni": "Chinese F · Xiaoni",
    "zf_xiaoxiao": "Chinese F · Xiaoxiao", "zf_xiaoyi": "Chinese F · Xiaoyi",
    "zm_yunjian": "Chinese M · Yunjian", "zm_yunxi": "Chinese M · Yunxi",
    "zm_yunxia": "Chinese M · Yunxia", "zm_yunyang": "Chinese M · Yunyang",
}
_VOICES = [Voice(id=voice_id, name=label) for voice_id, label in _VOICE_LABELS.items()]

_SAMPLE_RATE = 24_000
_DEFAULT_VOICE = "af_heart"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)

# Kokoro's voice prefix is also its KPipeline language code.
_LANG_CODES = frozenset("abefhijpz")


def _lang_for_voice(voice_id: str) -> str:
    prefix = voice_id[0] if voice_id else "a"
    return prefix if prefix in _LANG_CODES else "a"


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

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (audio_float32, sample_rate) without playing."""
        result = self._synthesize_array(text, voice_id or _DEFAULT_VOICE, params)
        return (result, _SAMPLE_RATE) if result is not None else None

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        if voice_id not in _VALID_VOICE_IDS:
            voice_id = _DEFAULT_VOICE
        lang_code = _lang_for_voice(voice_id)
        pipe = self._get_pipeline(lang_code)
        speed = _rate_to_speed(params.rate)
        volume = params.volume / 100.0
        chunks: list[np.ndarray] = []
        for _gs, _ps, audio in pipe(text=text, voice=voice_id, speed=speed):
            if audio is not None and len(audio) > 0:
                chunks.append(np.array(audio, dtype=np.float32) * volume)
        return np.concatenate(chunks) if chunks else None

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            audio_out = self._synthesize_array(text, voice_id, params)
            if audio_out is None or self._stop_requested.is_set():
                return
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
