"""VibeVoice-Realtime-0.5B TTS engine (Microsoft).

Auto-downloads model weights from HuggingFace Hub on first use
(microsoft/VibeVoice-Realtime-0.5B, ~2 GB). Single-speaker-per-voice —
unlike Kokoro/Piper/OuteTTS, this model doesn't clone from raw reference
audio at inference time; each voice is a precomputed KV-cache "prompt"
(.pt file) that Microsoft ships in the GitHub repo (not on the HF model
page), fetched on demand into models_root/ml/vibevoice_realtime/voices/.

Install: pip install "vibevoice[streamingtts] @ git+https://github.com/microsoft/VibeVoice.git"
Not on PyPI, and not in requirements.txt by default — see that file's
comment for why (heavy WebRTC/server deps unrelated to in-process use).

transformers pin (see requirements.txt's header comment for the full
story): the vibevoice package declares transformers<5.0.0, while
chatterbox-tts's own wheel metadata declares transformers==5.2.0 exactly.
requirements.txt pins transformers==4.51.3 (vibevoice's own streamingtts
extra pin) for the whole venv, deliberately overriding chatterbox-tts's
stated pin — verified for real (real from_pretrained() + real generate()
against real weights, for every engine in this app, see
docs/issues/issue_005_transformers_pin.md) that every engine actually
works fine under 4.51.3 despite what their metadata declares.

Known benign warning at model load: "Some weights ... were not initialized
from the model checkpoint ... newly initialized" for every
model.acoustic_tokenizer.encoder.* key. That submodule only encodes RAW
reference audio into tokens — this engine never calls that path, since
every voice is a precomputed KV-cache prompt (see above), not a raw
reference clip. Confirmed via real generation that output audio is normal
(non-silent, non-exploded amplitude) despite the warning — see
docs/issues/issue_005_transformers_pin.md.

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


def apply_volume(audio: np.ndarray, volume: int) -> np.ndarray:
    """Scale a real audio buffer by SpeakParams.volume (0..100) — a pure
    function (no model access) so it's unit-testable directly, same
    pattern as outetts_engine.py's resolve_speaker_name(). Deliberately
    NOT tested via two separate real generate() calls compared against
    each other (see test_vibevoice.py's test_real_synthesis_volume_scaling
    docstring) — VibeVoice's real autoregressive generation isn't
    reproducible enough call-to-call for that comparison to be meaningful;
    this function is what actually needs to be correct."""
    volume_scale = max(0.0, min(1.0, volume / 100.0))
    return audio * volume_scale


def _move_to_device(obj, device: str):
    """Recursively move every tensor inside a cached_prompt dict to the
    given device — including nested HF ModelOutput-like values.

    cached_prompt's structure (lm/tts_lm/neg_lm/neg_tts_lm) holds a mix of
    raw tensors and HF ModelOutput dict-subclass objects (which expose
    attribute access like `.past_key_values` but do NOT implement `.to()`
    themselves), and .pt files are always loaded to CPU first (see
    _get_cached_prompt) — this must run whenever the model itself is on a
    non-CPU device, or generate() fails with a "tensors on different
    devices" RuntimeError mixing the prompt's CPU KV-cache with the
    model's CUDA-resident new tokens.

    A plain isinstance(obj, dict) check to recurse would also match those
    ModelOutput subclasses and flatten them into a genuine plain dict via
    the comprehension, silently losing the attribute access generate()
    relies on ("'dict' object has no attribute 'past_key_values'"). So:
    recurse into any dict-like object's values, but reconstruct the
    original type afterward for anything that isn't an exact plain dict.
    """
    if isinstance(obj, dict):
        moved = {k: _move_to_device(v, device) for k, v in obj.items()}
        if type(obj) is dict:
            return moved
        try:
            return type(obj)(**moved)  # ModelOutput-style dataclass reconstruction
        except TypeError:
            return moved
    if type(obj) in (list, tuple):
        return type(obj)(_move_to_device(v, device) for v in obj)
    to_method = getattr(obj, "to", None)
    if callable(to_method) and not isinstance(obj, (str, int, float, bool)):
        try:
            return obj.to(device)
        except TypeError:
            pass
    # Fallback for HF Cache-like objects (e.g. DynamicCache): this
    # transformers version's Cache class has no working .to() — its real
    # state lives in plain-list attributes (key_cache/value_cache) on the
    # instance, invisible to the dict/list branches above since the Cache
    # object itself is neither. Mutate its __dict__ in place so every
    # tensor nested inside those lists actually moves.
    obj_dict = getattr(obj, "__dict__", None)
    if obj_dict:
        for k, v in list(obj_dict.items()):
            obj_dict[k] = _move_to_device(v, device)
    return obj


class VibeVoiceEngine(TtsEngine):
    """VibeVoice-Realtime-0.5B — class-level model singleton, daemon synth thread."""

    _model = None
    _processor = None
    _device = "cpu"
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

                # Weights live under .models (models_root), like every other
                # ML engine's weights_subpath in stacks.yaml — NOT the global
                # HF cache. snapshot_download() is idempotent (skips files
                # already present), so this is a no-op after the first run or
                # after install_dialog.py's Download button already fetched
                # the same target directory.
                local_dir = models_root() / "ml" / "vibevoice_realtime"
                local_dir.mkdir(parents=True, exist_ok=True)
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id=_HF_REPO, local_dir=str(local_dir), tqdm_class=None)

                _log.info("loading VibeVoice-Realtime-0.5B from %s (device=%s)", local_dir, device)
                VibeVoiceEngine._processor = VibeVoiceStreamingProcessor.from_pretrained(str(local_dir))
                try:
                    model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                        str(local_dir), torch_dtype=dtype, attn_implementation=attn_impl,
                    )
                except ImportError:
                    # flash_attention_2 requires the separate `flash_attn` package
                    # (not installed by requirements.txt or vibevoice's own
                    # extras) — matches the upstream demo script's own fallback
                    # behavior rather than hard-requiring a CUDA-only extra dep
                    # just to run on GPU at all.
                    _log.warn("flash_attention_2 unavailable (flash_attn not installed) — falling back to sdpa")
                    attn_impl = "sdpa"
                    model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                        str(local_dir), torch_dtype=dtype, attn_implementation=attn_impl,
                    )
                model.eval()
                if device == "cuda":
                    model = model.to(device)
                VibeVoiceEngine._model = model
                VibeVoiceEngine._device = device
                _log.info("VibeVoice model ready (device=%s)", device)
            return VibeVoiceEngine._model, VibeVoiceEngine._processor

    def _get_cached_prompt(self, voice_id: str):
        if voice_id in self._prompt_cache:
            return self._prompt_cache[voice_id]
        import torch
        pt_path = ensure_voice_downloaded(voice_id)
        # Always load to CPU first (map_location) — generate() needs the
        # cached prompt's tensors/KV-caches on the SAME device as the model
        # itself, which _move_to_device() below then handles explicitly.
        # Loading straight to a device string here would break on a machine
        # where the .pt file's tensors were saved from a different device
        # than what select_device() picks now.
        cached_prompt = torch.load(str(pt_path), map_location="cpu", weights_only=False)
        cached_prompt = _move_to_device(cached_prompt, VibeVoiceEngine._device)
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
        # The processor builds these tensors CPU-side regardless of where
        # cached_prompt's own tensors live (see _move_to_device's docstring)
        # — must move them to the model's device too, or generate() fails
        # mixing CPU input embeddings with a CUDA-resident model.
        inputs = _move_to_device(dict(inputs), VibeVoiceEngine._device)
        # generate() mutates all_prefilled_outputs' KV-cache in place
        # (appends each new token's key/value states) — passing the same
        # cached, reused voice-prompt object across multiple calls corrupts
        # it on the second call (stale/grown cache -> shape mismatch in
        # scaled_dot_product_attention). The upstream demo script guards
        # against exactly this with copy.deepcopy() before every generate()
        # call; self._prompt_cache must stay untouched across calls.
        import copy
        prefilled = copy.deepcopy(cached_prompt)
        with torch.no_grad():
            out = model.generate(
                input_ids=inputs.get("input_ids"),
                tts_lm_input_ids=inputs.get("tts_lm_input_ids"),
                tts_text_ids=inputs.get("tts_text_ids"),
                speech_input_mask=inputs.get("speech_input_mask"),
                attention_mask=inputs.get("attention_mask"),
                tts_lm_attention_mask=inputs.get("tts_lm_attention_mask"),
                all_prefilled_outputs=prefilled,
                generation_config={"do_sample": False},
                cfg_scale=1.0,
                tokenizer=processor.tokenizer,
                return_speech=True,
                stop_check_fn=self._stop_requested.is_set,
            )
        if not getattr(out, "speech_outputs", None):
            return None
        # .float() before .numpy() — numpy has no bfloat16 dtype, and
        # generate() returns bfloat16 output on CUDA (see the dtype chosen
        # in _get_model_and_processor); a bare .numpy() on that tensor
        # raises "Got unsupported ScalarType BFloat16".
        audio = out.speech_outputs[0].squeeze().float().detach().cpu().numpy().astype(np.float32)
        return apply_volume(audio, params.volume)

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
