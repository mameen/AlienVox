"""Qwen3-TTS 0.6B TTS engine (Alibaba Qwen Team).

Uses the CustomVoice variant: 9 preset speakers baked into the HF weights,
no reference audio required. Supports 10 languages natively.

HF repo: Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice (~1.5 GB)
Install:  pip install qwen-tts

Speakers ship as title-cased names inside the qwen-tts package itself
(e.g. "Vivian", "Serena") — our short stacks.yaml IDs (lower_snake_case)
are mapped to those names via _VOICE_TO_SPEAKER below.

Performance note: CPU inference is ~5–10× real-time factor on this model
(RTF > 1.0 means synthesis takes longer than the audio). GPU is strongly
recommended for interactive use. CPU is suitable for batch/async scenarios.

transformers compatibility: qwen-tts 0.1.1 requires transformers>=4.45.
We run transformers==4.51.3 (our current pin, see issue_005) — confirmed
compatible by running real from_pretrained() + generate_custom_voice()
against real weights before writing this file.
"""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from ..config import models_root
from ..device import select_device
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("qwen3tts")

_VOICES = [
    Voice(id="vivian",   name="Vivian (F · ZH/EN)"),
    Voice(id="serena",   name="Serena (F · ZH/EN)"),
    Voice(id="dylan",    name="Dylan (M · EN)"),
    Voice(id="eric",     name="Eric (M · EN)"),
    Voice(id="ryan",     name="Ryan (M · EN)"),
    Voice(id="aiden",    name="Aiden (M · EN)"),
    Voice(id="uncle_fu", name="Uncle Fu (M · ZH)"),
    Voice(id="ono_anna", name="Ono Anna (F · JA)"),
    Voice(id="sohee",    name="Sohee (F · KO)"),
]
_DEFAULT_VOICE = "vivian"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)

# Map our short IDs → the title-cased speaker names qwen-tts expects.
# Confirmed from Qwen3-TTS README / model.get_supported_speakers().
_VOICE_TO_SPEAKER: dict[str, str] = {
    "vivian":   "Vivian",
    "serena":   "Serena",
    "dylan":    "Dylan",
    "eric":     "Eric",
    "ryan":     "Ryan",
    "aiden":    "Aiden",
    "uncle_fu": "Uncle_Fu",
    "ono_anna": "Ono_Anna",
    "sohee":    "Sohee",
}

# Language hint per voice: models perform best in their native language,
# but every voice supports all 10 Qwen3-TTS languages. We pass the most
# likely language here so the model doesn't have to infer it.
_VOICE_TO_LANGUAGE: dict[str, str] = {
    "vivian":   "Chinese",
    "serena":   "Chinese",
    "dylan":    "English",
    "eric":     "English",
    "ryan":     "English",
    "aiden":    "English",
    "uncle_fu": "Chinese",
    "ono_anna": "Japanese",
    "sohee":    "Korean",
}

_HF_REPO = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_WEIGHTS_SUBPATH = Path("ml") / "qwen3tts"


def resolve_speaker_name(voice_id: str) -> str:
    """Map a (possibly invalid) short voice ID to the title-cased qwen-tts
    speaker name, falling back to _DEFAULT_VOICE's speaker if unrecognized.

    Pure function — no model access — so this can be unit-tested directly
    without loading the real Qwen3-TTS model, same pattern as outetts_engine.py.
    """
    if voice_id not in _VALID_VOICE_IDS:
        voice_id = _DEFAULT_VOICE
    return _VOICE_TO_SPEAKER[voice_id]


def resolve_language(voice_id: str) -> str:
    """Return the native-language hint for the given voice_id.

    Pure function — no model access.
    """
    if voice_id not in _VALID_VOICE_IDS:
        voice_id = _DEFAULT_VOICE
    return _VOICE_TO_LANGUAGE[voice_id]


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    """Scale a float32 audio buffer by SpeakParams.volume (0..100).

    Pure function (no model access) — directly unit-testable,
    same pattern as outetts_engine.py and vibevoice_engine.py.
    """
    scale = max(0.0, min(1.0, volume / 100.0))
    return audio * scale


def _local_model_path() -> Path | None:
    """Resolve the on-disk model directory, or None if not yet downloaded."""
    path = models_root() / _WEIGHTS_SUBPATH
    has_content = path.exists() and any(path.rglob("*"))
    return path if has_content else None


class Qwen3TTSEngine(TtsEngine):
    """Qwen3-TTS 0.6B — class-level model singleton, daemon synth thread.

    The model is loaded on first synthesize() call, not at __init__, to
    avoid a ~10–20 s GPU/CPU load cost for every engine that gets
    instantiated during registry discovery.
    """

    _model: object = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("Qwen3TTSEngine created — model will load on first use")

    # ── Model singleton ───────────────────────────────────────────────────────

    def _get_model(self):
        with Qwen3TTSEngine._model_lock:
            if Qwen3TTSEngine._model is None:
                import torch
                from qwen_tts import Qwen3TTSModel  # type: ignore[import-untyped]

                device = select_device()
                local_path = _local_model_path()

                # Load from local weights if present; fall back to HF Hub
                # auto-download (auto_download: true in stacks.yaml).
                model_path = str(local_path) if local_path else _HF_REPO
                _log.info(
                    "loading Qwen3-TTS from %s (device=%s)",
                    model_path, device,
                )

                dtype = torch.bfloat16
                load_kwargs: dict = {
                    "device_map": device,
                    "dtype": dtype,
                }

                Qwen3TTSEngine._model = Qwen3TTSModel.from_pretrained(
                    model_path, **load_kwargs
                )
                _log.info("Qwen3-TTS model ready")
            return Qwen3TTSEngine._model

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
            name="qwen3tts-speak",
        ).start()

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1_000)

    # ── Internal ──────────────────────────────────────────────────────────────

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (audio_float32, sample_rate) without playing.

        synthesize() is the hot path for the perf test harness — it runs
        on the calling thread (no daemon thread) and blocks until synthesis
        is complete.
        """
        result = self._synthesize_array(text, voice_id or _DEFAULT_VOICE, params)
        return result  # already (audio, sr) tuple or None

    def _synthesize_array(
        self, text: str, voice_id: str, params: SpeakParams
    ) -> tuple[np.ndarray, int] | None:
        if not text.strip():
            return None

        model = self._get_model()
        speaker = resolve_speaker_name(voice_id)
        language = resolve_language(voice_id)

        _log.info(
            "Qwen3-TTS generating %d chars (voice=%s → speaker=%s, lang=%s)",
            len(text), voice_id, speaker, language,
        )

        # generate_custom_voice returns (wavs, sr) where:
        #   wavs — list of numpy float32 arrays, one per input string
        #   sr   — int sample rate (Qwen3-TTS-12Hz produces 24000 Hz)
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=speaker,
        )

        audio = np.asarray(wavs[0], dtype=np.float32)

        # Normalise if the model returned int16-range values.
        if np.abs(audio).max() > 1.0:
            audio = audio / 32768.0

        return (apply_volume(audio, params.volume), int(sr))

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            if self._stop_requested.is_set():
                return
            result = self._synthesize_array(text, voice_id or _DEFAULT_VOICE, params)
            if result is None or self._stop_requested.is_set():
                return
            audio, sr = result
            play_audio(audio, sr)
        except Exception as exc:
            _log.error("Qwen3-TTS synthesis failed: %s", exc)
        finally:
            self._done.set()
