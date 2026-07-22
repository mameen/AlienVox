"""VibeVoice-Realtime-0.5B TTS engine (Microsoft).

Auto-downloads model weights from HuggingFace Hub on first use
(microsoft/VibeVoice-Realtime-0.5B, ~2 GB). Single-speaker-per-voice —
unlike Kokoro/Piper/OuteTTS, this model doesn't clone from raw reference
audio at inference time; each voice is a precomputed KV-cache "prompt"
(.pt file) that Microsoft ships in the GitHub repo (not on the HF model
page), fetched on demand into models_root/ml/vibevoice_realtime/voices/.

Install: pip install "vibevoice[streamingtts] @ git+https://github.com/microsoft/VibeVoice.git"
Not on PyPI, and not in requirements-ml.txt by default — see that file's
comment for why (heavy WebRTC/server deps unrelated to in-process use).

Performance note (see docs/issues/todo_006.md for the full writeup):
measured RTF ~2.5x on CPU (i.e. NOT real-time) — Microsoft's own docs only
validate real-time performance on NVIDIA T4 / Mac M4 Pro. Runs fine on
CPU, just slower than the "Realtime" name suggests; select_device() picks
CUDA automatically when available.
"""
from __future__ import annotations

import threading
import urllib.request

import numpy as np

from .. import logger as _logger_mod
from ..audio_player import play_audio, stop_playback
from ..config import models_root
from ..device import select_device
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("vibevoice")

_HF_REPO = "microsoft/VibeVoice-Realtime-0.5B"
_SAMPLE_RATE = 24_000
_DEFAULT_VOICE = "carter"

# Preset voice IDs -> the .pt filename Microsoft ships under
# demo/voices/streaming_model/ in the GitHub repo (NOT on the HF model
# page — a separate download, see module docstring).
_VOICE_TO_PT: dict[str, str] = {
    "carter": "en-Carter_man.pt",
    "davis":  "en-Davis_man.pt",
    "frank":  "en-Frank_man.pt",
    "mike":   "en-Mike_man.pt",
    "emma":   "en-Emma_woman.pt",
    "grace":  "en-Grace_woman.pt",
}
_VOICES = [
    Voice(id="carter", name="Carter (M)"),
    Voice(id="davis",  name="Davis (M)"),
    Voice(id="frank",  name="Frank (M)"),
    Voice(id="mike",   name="Mike (M)"),
    Voice(id="emma",   name="Emma (F)"),
    Voice(id="grace",  name="Grace (F)"),
]
_VALID_VOICE_IDS: frozenset[str] = frozenset(v.id for v in _VOICES)

_VOICE_PT_BASE_URL = (
    "https://raw.githubusercontent.com/microsoft/VibeVoice/main/"
    "demo/voices/streaming_model/"
)


def voices_dir(models_root_override=None):
    return models_root(models_root_override) / "ml" / "vibevoice_realtime" / "voices"


def ensure_voice_downloaded(voice_id: str, models_root_override=None):
    """Download a preset voice's .pt file if not already cached. Returns its path."""
    filename = _VOICE_TO_PT.get(voice_id, _VOICE_TO_PT[_DEFAULT_VOICE])
    dest_dir = voices_dir(models_root_override)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if not dest.exists():
        _log.info("downloading VibeVoice preset voice %s", filename)
        urllib.request.urlretrieve(_VOICE_PT_BASE_URL + filename, str(dest))
    return dest


class VibeVoiceEngine(TtsEngine):
    """VibeVoice-Realtime-0.5B — class-level model singleton, daemon synth thread."""

    _model = None
    _processor = None
    _model_lock = threading.Lock()

    def __init__(self) -> None:
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        self._prompt_cache: dict[str, object] = {}  # voice_id -> loaded cached_prompt
        _log.info("VibeVoiceEngine created — model will auto-download on first use")

    # ── Model singleton ───────────────────────────────────────────────────────

    def _get_model_and_processor(self):
        with VibeVoiceEngine._model_lock:
            if VibeVoiceEngine._model is None:
                import torch
                from vibevoice.modular.modeling_vibevoice_streaming_inference import (
                    VibeVoiceStreamingForConditionalGenerationInference,
                )
                from vibevoice.processor.vibevoice_streaming_processor import (
                    VibeVoiceStreamingProcessor,
                )

                device = select_device()
                dtype = torch.bfloat16 if device == "cuda" else torch.float32
                attn_impl = "flash_attention_2" if device == "cuda" else "sdpa"
                _log.info("loading VibeVoice-Realtime-0.5B from %s (device=%s)", _HF_REPO, device)
                VibeVoiceEngine._processor = VibeVoiceStreamingProcessor.from_pretrained(_HF_REPO)
                model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                    _HF_REPO, torch_dtype=dtype, attn_implementation=attn_impl,
                )
                model.eval()
                if device == "cuda":
                    model = model.to(device)
                VibeVoiceEngine._model = model
                _log.info("VibeVoice model ready (device=%s)", device)
            return VibeVoiceEngine._model, VibeVoiceEngine._processor

    def _get_cached_prompt(self, voice_id: str):
        if voice_id in self._prompt_cache:
            return self._prompt_cache[voice_id]
        import torch
        pt_path = ensure_voice_downloaded(voice_id)
        cached_prompt = torch.load(str(pt_path), map_location="cpu", weights_only=False)
        self._prompt_cache[voice_id] = cached_prompt
        return cached_prompt

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
            name="vibevoice-speak",
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

        import torch

        model, processor = self._get_model_and_processor()
        cached_prompt = self._get_cached_prompt(voice_id)

        _log.info("VibeVoice generating %d chars (voice=%s)", len(text), voice_id)
        inputs = processor.process_input_with_cached_prompt(
            text=text, cached_prompt=cached_prompt, return_tensors="pt",
        )
        with torch.no_grad():
            out = model.generate(
                input_ids=inputs.get("input_ids"),
                tts_lm_input_ids=inputs.get("tts_lm_input_ids"),
                tts_text_ids=inputs.get("tts_text_ids"),
                speech_input_mask=inputs.get("speech_input_mask"),
                attention_mask=inputs.get("attention_mask"),
                tts_lm_attention_mask=inputs.get("tts_lm_attention_mask"),
                all_prefilled_outputs=cached_prompt,
                generation_config={"do_sample": False},
                cfg_scale=1.0,
                tokenizer=processor.tokenizer,
                return_speech=True,
                stop_check_fn=self._stop_requested.is_set,
            )
        if not getattr(out, "speech_outputs", None):
            return None
        audio = out.speech_outputs[0].squeeze().detach().cpu().numpy().astype(np.float32)
        volume_scale = max(0.0, min(1.0, params.volume / 100.0))
        return audio * volume_scale

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            if self._stop_requested.is_set():
                return
            audio = self._synthesize_array(text, voice_id, params)
            if audio is None or self._stop_requested.is_set():
                return
            play_audio(audio, _SAMPLE_RATE)
        except Exception as exc:
            _log.error("VibeVoice synthesis failed: %s", exc)
        finally:
            self._done.set()
