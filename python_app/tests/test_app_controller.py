"""Tests for AppController — the only thing that mutates AppState.

These verify the two bug classes this whole MVC refactor exists to close
for good:
  1. engine not reloading when the active model/stack changes
  2. persisted user.yaml holding an inconsistent model/voice pair (the
     "model=chatterbox, voice=af_bella" bug reported multiple times)

Real ML engines are never loaded here — AppController._load_engine is
monkeypatched to return a lightweight fake, since these tests are about
orchestration (does the right method get called at the right time), not
about any particular engine's synthesis behaviour.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.control.app_controller import AppController, build_speak_params
from src.control.telemetry import Telemetry
from src.engines.registry import ModelInfo, StackInfo
from src.model.app_state import AppState


def _test_telemetry() -> Telemetry:
    """Telemetry writing to a throwaway file — avoids polluting real
    session logs and avoids requiring a callable sink (Telemetry's sink
    is a Path, not a callback)."""
    tmp = Path(tempfile.gettempdir()) / f"alienvox-test-telemetry-{id(object())}.jsonl"
    return Telemetry(sink=tmp)


class _FakeEngine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.stopped = False

    def list_voices(self):
        class _V:
            def __init__(self, id_, name_):
                self.id, self.name = id_, name_
        return [_V("v1", "Voice One")]

    def stop(self) -> None:
        self.stopped = True


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
    ]


def _cfg(**overrides) -> dict:
    base = {
        "engine": "ml", "model": "kokoro", "voice": "af_heart",
        "rate": 0, "pitch": 0, "volume": 100,
        "hotkey": "<ctrl>+<esc>", "ttl_seconds": 30,
    }
    base.update(overrides)
    return base


def _make_controller(monkeypatch, *, cfg=None, extra_cfg=None) -> AppController:
    state = AppState(_stacks(), cfg or _cfg())
    calls: list[tuple[str, str]] = []

    def _fake_load_engine(self, stack_id, model_id=""):
        calls.append((stack_id, model_id))
        return _FakeEngine(f"{stack_id}:{model_id}")

    monkeypatch.setattr(AppController, "_load_engine", _fake_load_engine)
    ctrl = AppController(state, _test_telemetry(), extra_cfg=extra_cfg)
    ctrl._load_calls = calls  # stash for assertions
    return ctrl


def test_engine_loaded_on_construction(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    assert ctrl.engine is not None
    assert ctrl.engine.name == "ml:kokoro"
    assert ctrl._load_calls == [("ml", "kokoro")]


def test_select_model_reloads_engine(monkeypatch):
    """The exact bug that was reported: switching models via the UI must
    actually reload the engine, not just update displayed state."""
    ctrl = _make_controller(monkeypatch)
    old_engine = ctrl.engine

    ctrl.select_model("chatterbox", voice_id="default")

    assert ctrl.engine is not old_engine
    assert ctrl.engine.name == "ml:chatterbox"
    assert old_engine.stopped is True
    assert ctrl.state.active_model == "chatterbox"
    assert ctrl.state.voice == "default"


def test_select_model_persists_consistent_model_voice_pair(monkeypatch):
    """Structural regression test for 'model=chatterbox, voice=af_bella':
    after switching models, the persisted patch must never mix a model id
    from one model with a voice id from another."""
    persisted: list[dict] = []
    ctrl = _make_controller(monkeypatch)
    monkeypatch.setattr(
        "src.control.app_controller.save_user_override",
        lambda patch, **kw: persisted.append(dict(patch)),
    )

    ctrl.select_model("chatterbox", voice_id="default")

    assert persisted, "expected at least one persisted patch"
    last = persisted[-1]
    assert last["model"] == "chatterbox"
    assert last["voice"] == "default"


def test_select_model_noop_when_already_active(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    old_engine = ctrl.engine
    ctrl.select_model("kokoro")  # already active
    assert ctrl.engine is old_engine
    assert ctrl._load_calls == [("ml", "kokoro")]  # no extra reload


def test_select_stack_switch_reloads_engine_and_resets_model(monkeypatch):
    stacks = _stacks() + [StackInfo(id="sapi5", name="SAPI 5", available=True, models=[])]
    state = AppState(stacks, _cfg())
    calls = []
    monkeypatch.setattr(
        AppController, "_load_engine",
        lambda self, sid, mid="": calls.append((sid, mid)) or _FakeEngine(f"{sid}:{mid}"),
    )
    ctrl = AppController(state, _test_telemetry())

    ctrl.select_stack("sapi5", voice_id="sapi-voice-1")

    assert ctrl.state.active_stack == "sapi5"
    assert ctrl.state.active_model == ""
    assert ctrl.state.voice == "sapi-voice-1"
    assert calls[-1] == ("sapi5", "")


def test_build_speak_params_includes_model_extra_controls(monkeypatch):
    ctrl = _make_controller(
        monkeypatch,
        cfg=_cfg(engine="ml", model="piper", voice="v1"),
        extra_cfg={"noise_scale": 0.5, "noise_w": 0.8, "sentence_silence": 0.2, "unrelated": 1},
    )
    params = build_speak_params(ctrl.state, ctrl._extra_cfg)
    assert params.extra == {"noise_scale": 0.5, "noise_w": 0.8, "sentence_silence": 0.2}


def test_load_settings_from_applies_patch_via_state_signals(monkeypatch, tmp_path):
    ctrl = _make_controller(monkeypatch)
    persisted: list[dict] = []
    monkeypatch.setattr(
        "src.control.app_controller.save_user_override",
        lambda patch, **kw: persisted.append(dict(patch)),
    )

    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text("engine: ml\nmodel: chatterbox\nvoice: default\n", encoding="utf-8")

    ctrl.load_settings_from(yaml_path)

    assert ctrl.state.active_model == "chatterbox"
    assert ctrl.state.voice == "default"
    assert ctrl.engine.name == "ml:chatterbox"


def test_play_enhanced_async_calls_speak_with_heuristic_enhance(monkeypatch):
    """Play Enhanced is a one-shot action, not a persisted mode — it must
    request enhance='heuristic' for this call only, via the normal speak()
    command, not some separate AppState toggle."""
    ctrl = _make_controller(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(ctrl, "speak", lambda *a, **kw: calls.append((a, kw)))

    ctrl.play_enhanced_async("some text")
    import time as _time
    for _ in range(50):
        if calls:
            break
        _time.sleep(0.01)

    assert calls, "speak() was never called by play_enhanced_async's thread"
    args, kwargs = calls[0]
    assert args[0] == "some text"
    assert args[1] is True  # restart=True
    assert kwargs.get("enhance") == "heuristic"


def test_play_async_does_not_enhance(monkeypatch):
    """The regular Play button must remain unaffected by Play Enhanced —
    no enhance kwarg means AppController.speak's own 'none' default."""
    ctrl = _make_controller(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(ctrl, "speak", lambda *a, **kw: calls.append((a, kw)))

    ctrl.play_async("some text")
    import time as _time
    for _ in range(50):
        if calls:
            break
        _time.sleep(0.01)

    assert calls, "speak() was never called by play_async's thread"
    args, kwargs = calls[0]
    assert "enhance" not in kwargs


def test_speak_enhanced_async_calls_speak_with_heuristic_enhance_and_toggle_behavior(monkeypatch):
    """The Play Enhanced global hotkey mirrors speak_async's toggle
    behavior (restart=False, text=None captures selection) but with
    enhance='heuristic' — same relationship play_enhanced_async has to
    play_async, just for the hotkey/tray path instead of the toolbar."""
    ctrl = _make_controller(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(ctrl, "speak", lambda *a, **kw: calls.append((a, kw)))

    ctrl.speak_enhanced_async()
    import time as _time
    for _ in range(50):
        if calls:
            break
        _time.sleep(0.01)

    assert calls, "speak() was never called by speak_enhanced_async's thread"
    args, kwargs = calls[0]
    assert args[0] is None
    assert args[1] is False  # restart=False, toggle behavior
    assert kwargs.get("enhance") == "heuristic"


def test_play_sample_async_speaks_fixed_sample_text(monkeypatch):
    """Play Sample ignores editor content entirely — it always speaks
    SAMPLE_TEXT with the active voice, restart=True (interrupts anything
    currently playing), no enhancement."""
    from src.control.app_controller import SAMPLE_TEXT
    ctrl = _make_controller(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(ctrl, "speak", lambda *a, **kw: calls.append((a, kw)))

    ctrl.play_sample_async()
    import time as _time
    for _ in range(50):
        if calls:
            break
        _time.sleep(0.01)

    assert calls, "speak() was never called by play_sample_async's thread"
    args, kwargs = calls[0]
    assert args[0] == SAMPLE_TEXT
    assert args[1] is True  # restart=True
    assert "enhance" not in kwargs


def test_debug_mode_off_never_records_text(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    ctrl.engine = None  # skip the actual engine.speak() call path
    events: list[dict] = []
    monkeypatch.setattr(ctrl.telemetry, "emit", lambda event, **kw: events.append(kw))

    ctrl._speak_locked("hello  world", "heuristic")

    triggered = next(e for e in events if True)  # only one emit() call reached (engine is None)
    assert "text" not in triggered
    assert "enhanced_text" not in triggered
    assert triggered["text_chars"] == len("hello  world")


def test_debug_mode_on_records_raw_and_enhanced_text(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    ctrl._debug = True
    ctrl.engine = None
    events: list[dict] = []
    monkeypatch.setattr(ctrl.telemetry, "emit", lambda event, **kw: events.append(kw))

    ctrl._speak_locked("hello  world", "heuristic")

    triggered = events[0]
    assert triggered["text"] == "hello  world"  # original, pre-enhancement
    assert triggered["enhanced_text"] == "hello world."  # post-enhancement


def test_debug_mode_on_without_enhancement_records_text_but_not_enhanced_text(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    ctrl._debug = True
    ctrl.engine = None
    events: list[dict] = []
    monkeypatch.setattr(ctrl.telemetry, "emit", lambda event, **kw: events.append(kw))

    ctrl._speak_locked("hello world", "none")

    triggered = events[0]
    assert triggered["text"] == "hello world"
    assert "enhanced_text" not in triggered


def test_enhance_text_none_strategy_passes_through(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    text, used = ctrl._enhance_text("foo  bar", "none")
    assert text == "foo  bar"
    assert used == "none"


def test_enhance_text_heuristic_strategy_applies_rules(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    text, used = ctrl._enhance_text("foo  bar", "heuristic")
    assert text == "foo bar."
    assert used == "heuristic"


def test_enhance_text_llm_strategy_falls_back_to_heuristic(monkeypatch):
    """llm_enhance isn't implemented yet (ADR-012 open) — the Controller
    must fall back to heuristic rather than propagating the failure or
    silently returning unenhanced text."""
    ctrl = _make_controller(monkeypatch)
    text, used = ctrl._enhance_text("foo  bar", "llm")
    assert text == "foo bar."
    assert used == "llm_fallback_heuristic"
