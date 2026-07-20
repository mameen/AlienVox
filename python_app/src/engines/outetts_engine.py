"""OuteTTS 0.5B real-time TTS engine (OuteAI).

Auto-downloads from HuggingFace Hub on first use (OuteAI/OuteTTS-0.3-500M).
Runs real-time on CPU; GPU accelerates inference further.
Uses built-in speaker presets — no reference audio required.

Install: pip install outetts

Note: outetts>=0.4.0 requires transformers<5 / older protobuf, which
directly conflicts with chatterbox-tts (pinned to transformers==5.2.0) and
onnxruntime (needs protobuf>=4.25, used by piper-tts). requirements.txt
pins outetts>=0.3.0 for this reason, and this engine targets 0.3.x's actual
API: outetts.InterfaceHF(model_version, cfg) is a *factory function*
(there is no outetts.Interface/outetts.Backend in this version), and
generate() takes a single GenerationConfig object, not kwargs.
"""
from __future__ import annotations

import threading

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from ..device import select_device
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("outetts")

_VOICES = [
    Voice(id="male_1",   name="Male 1"),
    Voice(id="male_2",   name="Male 2"),
    Voice(id="male_3",   name="Male 3"),
    Voice(id="female_1", name="Female 1"),
]
_DEFAULT_VOICE = "male_1"
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)
_SAMPLE_RATE = 44_100  # ModelOutput always resamples to this, regardless of the model's native rate
_HF_REPO = "OuteAI/OuteTTS-0.3-500M"
_MODEL_VERSION = "0.3"  # matches outetts.interface.MODEL_CONFIGS key for this repo

# outetts's built-in default speakers are language-prefixed (en_male_1,
# en_female_1, ...) and only include ONE English female preset — our simple
# IDs are mapped to the real speaker names here so stacks.yaml/the UI don't
# need to leak outetts's naming scheme.
_VOICE_TO_SPEAKER = {
    "male_1":   "en_male_1",
    "male_2":   "en_male_2",
    "male_3":   "en_male_3",
    "female_1": "en_female_1",
}


class OuteTTSEngine(TtsEngine):
    """OuteTTS 0.5B — single class-level model singleton, daemon synth thread."""

    _interface: object = None
    _interface_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("OuteTTSEngine created — model will auto-download on first use")

    # ── Model singleton ───────────────────────────────────────────────────────

    def _get_interface(self):
        with OuteTTSEngine._interface_lock:
            if OuteTTSEngine._interface is None:
                import outetts
                device = select_device()
                _log.info("loading OuteTTS from %s (device=%s)", _HF_REPO, device)
                # model_version "0.3" requires an explicit tokenizer_path (no
                # default lookup) — the repo itself hosts a matching tokenizer.
                cfg = outetts.HFModelConfig_v2(model_path=_HF_REPO, tokenizer_path=_HF_REPO, device=device)
                OuteTTSEngine._interface = outetts.InterfaceHF(model_version=_MODEL_VERSION, cfg=cfg)
                _log.info("OuteTTS model ready")
            return OuteTTSEngine._interface

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
            name="outetts-speak",
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
        import outetts

        interface = self._get_interface()
        speaker_name = _VOICE_TO_SPEAKER[voice_id]
        speaker = interface.load_default_speaker(name=speaker_name)
        _log.info("OuteTTS generating %d chars (voice=%s -> %s)", len(text), voice_id, speaker_name)
        gen_config = outetts.GenerationConfig(
            text=text, speaker=speaker,
            temperature=0.1, repetition_penalty=1.1, max_length=4096,
        )
        output = interface.generate(config=gen_config)
        # output.audio is a torch.Tensor shaped [batch, samples], already
        # resampled to _SAMPLE_RATE by ModelOutput — see class docstring above.
        audio = output.audio[0].detach().cpu().numpy().astype(np.float32)
        if np.abs(audio).max() > 1.0:
            audio = audio / 32768.0
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
            _log.error("OuteTTS synthesis failed: %s", exc)
        finally:
            self._done.set()
