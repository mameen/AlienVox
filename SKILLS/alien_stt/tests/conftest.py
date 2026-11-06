#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared fixtures and skip rules for the alien_stt tests.

Philosophy (same as the rest of this repository): no mocking of internal code.
The audio is a real recording of speech (`assets/sample_speech.wav`); ffmpeg and
the Whisper model are real. A test that needs something the machine lacks
(ffmpeg, torch, cached weights) *skips* with the reason; it never fails for that
and it never downloads anything.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

import numpy as np
import pytest
import soundfile as sf

SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

SAMPLE = SKILL_ROOT / "assets" / "sample_speech.wav"
SAMPLE_WORDS = ("welcome", "performance", "test")          # words the sample says

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
requires_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


def _model_cached(model_id: str) -> bool:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    from check_setup import model_cached
    return model_cached(model_id)


def _torch_ok() -> bool:
    try:
        import torch, transformers  # noqa: F401
        return True
    except Exception:
        return False


#: A fast cached Whisper model, so the real-model tests stay quick.
TEST_MODEL = "openai/whisper-large-v3-turbo"
requires_model = pytest.mark.skipif(
    not (HAVE_FFMPEG and _torch_ok() and _model_cached(TEST_MODEL)),
    reason=f"needs ffmpeg, torch+transformers and {TEST_MODEL} already in the Hugging Face cache",
)


@pytest.fixture(scope="session")
def sample_wav() -> pathlib.Path:
    return SAMPLE


@pytest.fixture()
def gapped_wav(tmp_path) -> pathlib.Path:
    """Real speech, 3 s of silence, real speech, 3 s of silence, real speech: three utterances with clear gaps."""
    data, sr = sf.read(str(SAMPLE), dtype="float32")
    gap = np.zeros(int(3 * sr), dtype="float32")
    out = tmp_path / "gapped.wav"
    sf.write(str(out), np.concatenate([data, gap, data, gap, data]), sr)
    return out


@pytest.fixture(scope="session")
def engine():
    """One real engine for the whole session: the model loads once."""
    from alienstt import get_engine
    return get_engine("whisper", model=TEST_MODEL)
