"""F5-TTS zero-shot voice cloning engine (SWivid/F5-TTS).

Auto-downloads model weights on first use.  Preset reference voices are
stored in  .models/ml/f5tts/voices/<id>.wav  and downloaded from HuggingFace
the first time that voice is selected via the Install dialog.

F5-TTS requires a short reference audio clip (~3–10 s) plus its transcript
to clone a voice.  The preset voices below ship with curated references.
Users may add their own by dropping <id>.wav + <id>.txt files into the
voices folder and restarting the app.

Install: pip install f5-tts
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

_log = _logger_mod.get_logger("f5tts")

# Preset voices — each requires a .wav + .txt reference pair in
# .models/ml/f5tts/voices/<id>.wav  and  .models/ml/f5tts/voices/<id>.txt
_VOICES = [
    Voice(id="en_female_calm",  name="English F · Calm"),
    Voice(id="en_male_warm",    name="English M · Warm"),
]
_DEFAULT_VOICE = "en_female_calm"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)
_SAMPLE_RATE = 24_000


def _voices_dir() -> Path:
    return models_root() / "ml" / "f5tts" / "voices"


def _ref_wav(voice_id: str) -> Path:
    return _voices_dir() / f"{voice_id}.wav"


def _ref_txt(voice_id: str) -> Path:
    return _voices_dir() / f"{voice_id}.txt"


class F5TTSEngine(TtsEngine):
    """F5-TTS zero-shot cloning engine — daemon synth thread, lazy model load."""

    _model: object = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("F5TTSEngine created — model will auto-download on first use")

    # ── Model singleton ───────────────────────────────────────────────────────

    def _get_model(self):
        with F5TTSEngine._model_lock:
            if F5TTSEngine._model is None:
                device = select_device()
                _log.info("loading F5-TTS model (may download ~1.2 GB, device=%s)", device)
                from f5_tts.api import F5TTS
                F5TTSEngine._model = F5TTS(model="F5TTS_v1_Base", device=device)
                _log.info("F5-TTS model ready")
            return F5TTSEngine._model

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
            name="f5tts-speak",
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
        return result if result is not None else None

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        """Returns (audio_float32, sr) or None."""
        if not text.strip():
            return None
        if voice_id not in _VALID_VOICE_IDS:
            voice_id = _DEFAULT_VOICE
        ref_wav_path = _ref_wav(voice_id)
        if not ref_wav_path.exists():
            _log.error(
                "F5-TTS reference voice %r not found at %s — "
                "open the Install dialog to download preset voices",
                voice_id, ref_wav_path,
            )
            return None
        ref_txt_path = _ref_txt(voice_id)
        ref_text = ref_txt_path.read_text(encoding="utf-8").strip() if ref_txt_path.exists() else ""
        model = self._get_model()
        _log.info("F5-TTS generating %d chars (voice=%s)", len(text), voice_id)
        wav, sr, _ = model.infer(ref_file=str(ref_wav_path), ref_text=ref_text, gen_text=text, seed=42)
        audio = np.asarray(wav, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=0)
        volume_scale = max(0.0, min(1.0, params.volume / 100.0))
        return (audio * volume_scale, sr or _SAMPLE_RATE)

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
            _log.error("F5-TTS synthesis failed: %s", exc)
        finally:
            self._done.set()
