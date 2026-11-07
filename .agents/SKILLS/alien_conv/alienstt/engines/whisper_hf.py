#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Whisper speech recognition through Hugging Face `transformers`, run locally.

Local and offline
-----------------
Audio never leaves the machine. Model weights come from the Hugging Face cache
(``HF_HOME``); a model that is not cached is downloaded once on first use
(large-v3 is about 3 GB, turbo about 1.6 GB). To stay strictly offline after
that, set ``HF_HUB_OFFLINE=1``.

How long audio is handled
-------------------------
Whisper reads 30-second windows. For anything longer this engine uses the
model's own **long-form decoding** (a sliding window with a temperature
fallback and a no-speech check) and turns off `condition_on_prev_tokens`, which
feeds earlier text back in as a prompt. That feedback is the single biggest
source of the classic failures: a repeated paragraph, or a confident sentence
("subscribe to the channel") invented over silence. Turning it off costs a
little cross-sentence consistency and removes most of those failures, which is
the better trade for a draft a person will check.

Audio shorter than one window is padded with silence so it takes the same
code path as long audio, and any segment that starts inside the padding is
dropped. One path means one behaviour to test.

Choosing a model
----------------
See `MODEL_ALIASES`. In short: ``large-v3`` is the most accurate and the
default; ``large-v3-turbo`` is several times faster and a little less accurate
(more so on non-English); smaller models are for quick drafts and low-memory
machines; ``*.en`` models are English only and slightly better at English.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..base import SAMPLE_RATE, Segment, SttEngine, TranscribeOptions
from ..device import select_device

#: Default model: the most accurate openly available Whisper.
DEFAULT_MODEL = "openai/whisper-large-v3"

#: Short names accepted anywhere a model is asked for. A full Hugging Face id
#: (``org/name``) or a local folder path is always accepted as well.
MODEL_ALIASES = {
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
    "turbo": "openai/whisper-large-v3-turbo",
    "large-v2": "openai/whisper-large-v2",
    "medium": "openai/whisper-medium",
    "small": "openai/whisper-small",
    "base": "openai/whisper-base",
    "tiny": "openai/whisper-tiny",
    "medium.en": "openai/whisper-medium.en",
    "small.en": "openai/whisper-small.en",
    "base.en": "openai/whisper-base.en",
    "tiny.en": "openai/whisper-tiny.en",
    "distil-large-v3": "distil-whisper/distil-large-v3",
}

_WINDOW_SECONDS = 30.0


def resolve_model(name: str) -> str:
    """Map an alias such as ``"turbo"`` to a Hugging Face id; pass anything else through."""
    return MODEL_ALIASES.get(name, name)


class WhisperHFEngine(SttEngine):
    """Whisper via `transformers`. Loads lazily, caches the model for reuse.

    One instance can transcribe many files; the model is loaded on the first
    call and kept, so a batch pays the load cost once.
    """

    name = "whisper"

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "auto") -> None:
        self._model_id = resolve_model(model)
        self._device = select_device(device)
        self._proc: Any = None
        self._model: Any = None
        self._dtype: Any = None

    # -- provenance ---------------------------------------------------------
    @property
    def model_name(self) -> str:
        return self._model_id

    @property
    def device_name(self) -> str:
        return self._device

    # -- loading ------------------------------------------------------------
    def load(self) -> None:
        """Load processor and model if not already loaded. Safe to call twice."""
        if self._model is not None:
            return
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        from transformers.utils import logging as hf_logging

        # Keep the console readable: errors only, no per-tensor progress bars.
        # Callers who want the library's chatter can raise the level again.
        hf_logging.set_verbosity_error()
        hf_logging.disable_progress_bar()
        self._dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._proc = WhisperProcessor.from_pretrained(self._model_id)
        try:
            model = WhisperForConditionalGeneration.from_pretrained(self._model_id, dtype=self._dtype)
        except TypeError:                                # transformers < 4.56 spells it torch_dtype
            model = WhisperForConditionalGeneration.from_pretrained(self._model_id, torch_dtype=self._dtype)
        self._model = model.to(self._device).eval()

    # -- features -----------------------------------------------------------
    def _features(self, audio: np.ndarray, pad_to_long_form: bool) -> dict[str, Any]:
        """Build model inputs. With `pad_to_long_form`, pad short audio so it takes the long-form path."""
        if pad_to_long_form:
            need = int((_WINDOW_SECONDS + 0.5) * SAMPLE_RATE)
            if audio.size < need:
                audio = np.concatenate([audio, np.zeros(need - audio.size, dtype=audio.dtype)])
            feats = self._proc(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt", truncation=False,
                               padding="longest", return_attention_mask=True)
        else:
            feats = self._proc(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        return {k: (v.to(self._device, self._dtype) if k == "input_features" else v.to(self._device))
                for k, v in feats.items()}

    # -- engine contract ----------------------------------------------------
    def transcribe(self, audio: np.ndarray, options: TranscribeOptions) -> list[Segment]:
        """Transcribe one in-memory piece of 16 kHz mono audio. See the module docstring."""
        import torch

        self.load()
        duration = audio.size / SAMPLE_RATE
        feats = self._features(audio, pad_to_long_form=True)
        kwargs: dict[str, Any] = dict(
            task=options.task,
            return_timestamps=True,
            return_segments=True,
            condition_on_prev_tokens=False,
            temperature=tuple(options.temperature),
            compression_ratio_threshold=options.compression_ratio_threshold,
            logprob_threshold=options.logprob_threshold,
            no_speech_threshold=options.no_speech_threshold,
            num_beams=max(1, options.beam_size),
        )
        if options.language:
            kwargs["language"] = options.language
        if options.prompt:
            kwargs["prompt_ids"] = self._proc.get_prompt_ids(options.prompt, return_tensors="pt").to(self._device)
        with torch.inference_mode():
            result = self._model.generate(**feats, **kwargs)

        segments: list[Segment] = []
        for seg in result["segments"][0]:
            text = self._proc.tokenizer.decode(seg["tokens"], skip_special_tokens=True).strip()
            if not text:
                continue
            start, end = float(seg["start"]), min(float(seg["end"]), duration)
            if start >= duration:                         # starts inside the padding we added
                continue
            segments.append(Segment(round(start, 2), round(end, 2), text))
        return segments

    def language_scores(self, audio: np.ndarray, top: int = 5) -> list[tuple[str, float]]:
        """Probability for each language Whisper knows, best first, limited to `top`.

        Runs one decoder step from the start-of-transcript token and takes the
        softmax over just the language tokens, so the numbers are real
        probabilities that sum to 1 across languages, not only a name.
        English-only models have no language tokens and return ``[("en", 1.0)]``.
        """
        import torch
        from transformers.models.whisper.tokenization_whisper import LANGUAGES

        self.load()
        if self._model_id.endswith(".en"):
            return [("en", 1.0)]
        codes = list(LANGUAGES.keys())
        tok = self._proc.tokenizer
        lang_ids = tok.convert_tokens_to_ids([f"<|{c}|>" for c in codes])
        head = audio[: int(_WINDOW_SECONDS * SAMPLE_RATE)]
        feats = self._features(head, pad_to_long_form=False)
        start_id = tok.convert_tokens_to_ids("<|startoftranscript|>")
        decoder_ids = torch.tensor([[start_id]], device=self._device)
        with torch.inference_mode():
            logits = self._model(input_features=feats["input_features"], decoder_input_ids=decoder_ids).logits[0, -1]
        probs = torch.softmax(logits[lang_ids].float(), dim=-1).cpu()
        order = torch.argsort(probs, descending=True)[: max(1, top)]
        return [(codes[int(i)], float(probs[int(i)])) for i in order]

    def detect_language(self, audio: np.ndarray) -> tuple[Optional[str], Optional[float]]:
        """Identify the spoken language from the first 30 seconds (best guess and its probability)."""
        scores = self.language_scores(audio, top=1)
        if not scores:
            return None, None
        code, prob = scores[0]
        return code, (None if self._model_id.endswith(".en") else prob)
