"""Tests for AppState — the single source of truth for AlienVox's active
stack/model/voice/params.

Requires a real QApplication (Signal/QObject need one running event-loop
process, even without showing any widgets).
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from src.model.app_state import AppState
from src.engines.registry import ModelInfo, StackInfo


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _stacks() -> list[StackInfo]:
    return [
        StackInfo(id="ml", name="ML / AI", available=True, models=[
            ModelInfo(id="kokoro", name="Kokoro-82M", available=True, voices=[
                {"id": "af_heart", "label": "AF Heart"},
            ]),
            ModelInfo(id="chatterbox", name="Chatterbox 0.5B", available=True, voices=[
                {"id": "default", "label": "Default"},
            ]),
        ]),
        StackInfo(id="sapi5", name="SAPI 5", available=True, models=[]),
    ]


def _cfg(**overrides) -> dict:
    base = {
        "engine": "ml", "model": "chatterbox", "voice": "default",
        "rate": 0, "pitch": 0, "volume": 100,
        "hotkey": "<ctrl>+<esc>", "ttl_seconds": 30,
    }
    base.update(overrides)
    return base


def test_initializes_from_cfg(qapp):
    state = AppState(_stacks(), _cfg())
    assert state.active_stack == "ml"
    assert state.active_model == "chatterbox"
    assert state.voice == "default"
    assert state.rate == 0
    assert state.volume == 100


def test_set_active_model_emits_signal_with_new_value(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.model_changed.connect(received.append)
    state.set_active_model("kokoro")
    assert received == ["kokoro"]
    assert state.active_model == "kokoro"


def test_set_active_model_noop_when_unchanged_does_not_emit(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.model_changed.connect(received.append)
    state.set_active_model("chatterbox")  # already the active model
    assert received == []


def test_set_voice_emits_signal(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.voice_changed.connect(received.append)
    state.set_voice("af_heart")
    assert received == ["af_heart"]


def test_set_params_batches_and_reports_only_changed_keys(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.params_changed.connect(received.append)
    state.set_params(rate=5, pitch=0, volume=80)  # pitch unchanged (already 0)
    assert len(received) == 1
    assert received[0] == {"rate": 5, "volume": 80}
    assert state.rate == 5
    assert state.volume == 80
    assert state.pitch == 0


def test_set_params_unknown_key_raises(qapp):
    state = AppState(_stacks(), _cfg())
    with pytest.raises(ValueError):
        state.set_params(nonexistent=1)


def test_to_cfg_patch_round_trips_active_state(qapp):
    state = AppState(_stacks(), _cfg())
    state.set_active_model("kokoro")
    state.set_voice("af_heart")
    state.set_params(rate=3)
    patch = state.to_cfg_patch()
    assert patch["engine"] == "ml"
    assert patch["model"] == "kokoro"
    assert patch["voice"] == "af_heart"
    assert patch["rate"] == 3


def test_load_cfg_patch_fires_signals_like_a_normal_change(qapp):
    """This is what makes Load Settings automatically resync every View —
    no separate manual resync step needed."""
    state = AppState(_stacks(), _cfg())
    stack_events, model_events, voice_events = [], [], []
    state.stack_changed.connect(stack_events.append)
    state.model_changed.connect(model_events.append)
    state.voice_changed.connect(voice_events.append)

    state.load_cfg_patch({"engine": "sapi5", "model": "", "voice": "some-sapi-voice"})

    assert stack_events == ["sapi5"]
    assert model_events == [""]
    assert voice_events == ["some-sapi-voice"]
    assert state.active_stack == "sapi5"


def test_set_live_voices_emits_catalog_changed(qapp):
    state = AppState(_stacks(), _cfg())
    fired = []
    state.catalog_changed.connect(lambda: fired.append(True))
    state.set_live_voices("sapi5", [{"id": "v1", "label": "Voice 1"}])
    assert fired == [True]
    assert state.live_voices_for("sapi5") == [{"id": "v1", "label": "Voice 1"}]


def test_model_info_looks_up_within_stack(qapp):
    state = AppState(_stacks(), _cfg())
    model = state.model_info("ml", "kokoro")
    assert model is not None
    assert model.name == "Kokoro-82M"
    assert state.model_info("ml", "nonexistent") is None


def test_speaking_and_error_are_not_persisted(qapp):
    """speaking/last_error are transient runtime status — to_cfg_patch
    must never include them, or a crash mid-speak would persist a stuck
    'speaking' flag."""
    state = AppState(_stacks(), _cfg())
    state.set_speaking(True)
    state.set_error("boom")
    patch = state.to_cfg_patch()
    assert "speaking" not in patch
    assert "last_error" not in patch
    assert "error" not in patch


def test_enhance_strategy_defaults_to_none(qapp):
    state = AppState(_stacks(), _cfg())
    assert state.enhance_strategy == "none"


def test_set_enhance_strategy_emits_signal(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.enhance_strategy_changed.connect(received.append)
    state.set_enhance_strategy("heuristic")
    assert received == ["heuristic"]
    assert state.enhance_strategy == "heuristic"


def test_set_enhance_strategy_unknown_value_raises(qapp):
    state = AppState(_stacks(), _cfg())
    with pytest.raises(ValueError):
        state.set_enhance_strategy("not-a-strategy")


def test_invalid_enhance_strategy_in_cfg_falls_back_to_none(qapp):
    state = AppState(_stacks(), _cfg(enhance_strategy="bogus"))
    assert state.enhance_strategy == "none"


def test_enhance_strategy_round_trips_through_cfg_patch(qapp):
    state = AppState(_stacks(), _cfg())
    state.set_enhance_strategy("heuristic")
    assert state.to_cfg_patch()["enhance_strategy"] == "heuristic"


def test_load_cfg_patch_applies_enhance_strategy(qapp):
    state = AppState(_stacks(), _cfg())
    received = []
    state.enhance_strategy_changed.connect(received.append)
    state.load_cfg_patch({"enhance_strategy": "heuristic"})
    assert received == ["heuristic"]
