"""Kokoro-82M TTS engine — the default engine in this library.

Adapted from `python_app/src/engines/kokoro_engine.py` — same synthesis
logic and voice roster, decoupled from the app's own `..logger`/`AppState`
so this file has zero dependency on `python_app` and works as a standalone
import from anywhere (the `alien_vox` skill, `python_mcp_server`, or your
own script).

Model: hexgrad/Kokoro-82M (Apache 2.0), via the `kokoro` PyPI package
(`pip install kokoro>=0.9.0`). Auto-downloads (~300 MB) from Hugging Face
Hub on first use via `kokoro.KPipeline(repo_id=...)` — no manual weight
management needed, and no dependency on any app-specific weights directory
(HF Hub's own cache, typically `~/.cache/huggingface`, handles it).

Default voice: `af_heart` ("American F · Heart") — matches the AlienVox
app's own `stacks.yaml` default for the `ml`/`kokoro` model.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from ..audio import play_audio, stop_playback
from ..base import SpeakParams, TtsEngine, Voice
from ..device import select_device

_log = logging.getLogger("alienvox_tts.kokoro")

VOICES = [
    Voice(id="af_heart",   name="American F · Heart"),
    Voice(id="af_bella",   name="American F · Bella"),
    Voice(id="af_nicole",  name="American F · Nicole"),
    Voice(id="am_adam",    name="American M · Adam"),
    Voice(id="am_michael", name="American M · Michael"),
    Voice(id="bf_emma",    name="British F · Emma"),
    Voice(id="bm_george",  name="British M · George"),
]

SAMPLE_RATE = 24_000
DEFAULT_VOICE = "af_heart"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in VOICES)
_HF_REPO = "hexgrad/Kokoro-82M"

# lang_code per voice-id prefix: 'a' = American English, 'b' = British English —
# Kokoro's KPipeline is loaded once per language, since the underlying model
# has separate front-end phonemization rules per language/accent.
_LANG_MAP = {"a": "a", "b": "b"}


def _lang_for_voice(voice_id: str) -> str:
    prefix = voice_id[0] if voice_id else "a"
    return _LANG_MAP.get(prefix, "a")


def _rate_to_speed(rate: int) -> float:
    """Convert this library's uniform -10..+10 rate scale to Kokoro's own
    0.5x..2.0x speed multiplier. Linear on each side of 0, meeting exactly
    at 1.0x (Kokoro's natural pace) when rate=0."""
    clamped = max(-10, min(10, rate))
    if clamped >= 0:
        return 1.0 + clamped * 0.1    # 0 -> 1.0x, 10 -> 2.0x
    return 1.0 + clamped * 0.05        # 0 -> 1.0x, -10 -> 0.5x


class KokoroEngine(TtsEngine):
    """Kokoro-82M — one KPipeline instance per language, lazily created and
    cached (thread-safe) on first use per language. A single engine
    instance is meant to be reused across multiple speak()/synthesize()
    calls, not recreated per call — recreating it would re-trigger the
    (cached, but still non-instant) model load every time.

    device: resolved ONCE at construction (KPipeline's own device is fixed
    at load time — there's no cheap way to move a loaded pipeline to a
    different device mid-process, so this engine doesn't pretend to
    support per-call device switching). Defaults to "cpu", matching the
    AlienVox project's established CPU-first default (see python_app's
    run.py `_resolve_device()`) — NOT `device.select_device()`'s own
    auto-prefer-GPU default, which is the right default for a caller that
    explicitly wants "best available," but the wrong default for a
    library whose callers (the alien_vox skill, python_mcp_server) should
    require an explicit opt-in to use a GPU, not silently get one.
    Pass device="gpu"/"cuda" to opt in — falls back to CPU automatically
    if no usable GPU is actually present.
    """

    def __init__(self, device: str = "cpu") -> None:
        self._device = select_device(prefer=device)
        self._pipeline_lock = threading.Lock()
        self._pipelines: dict[str, object] = {}  # lang_code -> KPipeline
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("KokoroEngine created (device=%s) — model will auto-download on first use", self._device)

    # ── Model loading ────────────────────────────────────────────────────

    def _get_pipeline(self, lang_code: str):
        with self._pipeline_lock:
            if lang_code not in self._pipelines:
                _log.info(
                    "loading KPipeline lang=%s device=%s (may download ~300MB weights)",
                    lang_code, self._device,
                )
                from kokoro import KPipeline
                pipe = KPipeline(lang_code=lang_code, repo_id=_HF_REPO, device=self._device)
                self._pipelines[lang_code] = pipe
                _log.info("KPipeline lang=%s ready", lang_code)
            return self._pipelines[lang_code]

    # ── TtsEngine API ─────────────────────────────────────────────────────

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Synthesizes then plays through the default audio output device,
        on a background thread — returns immediately. Call
        wait_until_done() to block until playback finishes, or use
        speak_sync() to do both in one call."""
        if not text:
            return
        self._done.clear()
        self._stop_requested.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id or DEFAULT_VOICE, params),
            daemon=True,
            name="kokoro-speak",
        ).start()

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (float32 numpy array, 24000) WITHOUT playing — the hook
        to use if you want raw audio (to save to a file, return over an
        API, etc.) rather than immediate local playback."""
        result = self._synthesize_array(text, voice_id or DEFAULT_VOICE, params)
        return (result, SAMPLE_RATE) if result is not None else None

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def pause(self) -> None:
        # sounddevice has no true pause/resume — stop is the closest
        # supported behavior (same as the app's own engine does).
        stop_playback()

    def resume(self) -> None:
        pass  # not supported — see pause()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1000.0)

    # ── Internal ──────────────────────────────────────────────────────────

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        if voice_id not in _VALID_VOICE_IDS:
            _log.warning("unknown voice_id=%r, falling back to %s", voice_id, DEFAULT_VOICE)
            voice_id = DEFAULT_VOICE
        lang_code = _lang_for_voice(voice_id)
        pipe = self._get_pipeline(lang_code)
        speed = _rate_to_speed(params.rate)
        volume_scale = max(0.0, min(1.0, params.volume / 100.0))

        chunks: list[np.ndarray] = []
        for _graphemes, _phonemes, audio in pipe(text=text, voice=voice_id, speed=speed):
            if audio is not None and len(audio) > 0:
                chunks.append(np.array(audio, dtype=np.float32) * volume_scale)
        return np.concatenate(chunks) if chunks else None

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            audio_out = self._synthesize_array(text, voice_id, params)
            if audio_out is None or self._stop_requested.is_set():
                return
            play_audio(audio_out, SAMPLE_RATE)
        except Exception as exc:
            _log.error("Kokoro speak failed: %s", exc)
        finally:
            self._done.set()
