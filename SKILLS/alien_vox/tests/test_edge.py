"""Tests for the networked `edge` engine. Pure-logic tests always run; the real
synthesis test needs `edge-tts` AND a network connection, and skips (not fails)
without either — no mocking, per this repo's anti-mocking philosophy."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alienvox_tts import DEFAULT_VOICES, ENGINES, SpeakParams
from alienvox_tts.engines.edge import EdgeEngine, _pitch_to_hz, _rate_to_percent


def _online() -> bool:
    try:
        socket.create_connection(("speech.platform.bing.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


def test_registered_with_its_own_default_voice():
    assert ENGINES["edge"] is EdgeEngine
    assert DEFAULT_VOICES["edge"] == "ar-SA-HamedNeural"


def test_rate_and_pitch_mapping():
    assert _rate_to_percent(0) == "+0%"
    assert _rate_to_percent(10) == "+100%"
    assert _rate_to_percent(-10) == "-50%"
    assert _rate_to_percent(99) == "+100%"
    assert _pitch_to_hz(0) == "+0Hz"
    assert _pitch_to_hz(-3) == "-15Hz"


def test_voice_roster_ids_are_well_formed():
    from alienvox_tts.engines.edge import _VOICE_ID_RE
    assert all(_VOICE_ID_RE.match(v.id) for v in EdgeEngine().list_voices())


def test_malformed_voice_raises_instead_of_falling_back():
    with pytest.raises(ValueError):
        EdgeEngine().synthesize("hello", "af_heart", SpeakParams())


def test_empty_text_returns_none():
    assert EdgeEngine().synthesize("   ", "ar-SA-HamedNeural", SpeakParams()) is None


@pytest.mark.skipif(not _online(), reason="no network: edge engine needs Microsoft's online service")
def test_real_arabic_synthesis():
    pytest.importorskip("edge_tts")
    audio, sr = EdgeEngine().synthesize("مرحبا بكم", "ar-SA-HamedNeural", SpeakParams())
    assert sr == 24000 and audio.dtype == np.float32 and len(audio) / sr > 0.5
    assert float(np.abs(audio).max()) > 0.01
