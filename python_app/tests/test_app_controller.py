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

from src.control.app_controller import SAMPLE_TEXT as _SAMPLE_TEXT_FOR_TEST
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
        self.spoken: list[tuple[str, str]] = []  # (text, voice_id)

    def list_voices(self):
        class _V:
            def __init__(self, id_, name_):
                self.id, self.name = id_, name_
        return [_V("v1", "Voice One")]

    def speak(self, text, voice_id, params) -> None:
        self.spoken.append((text, voice_id))

    def wait_until_done(self, timeout_ms: int) -> bool:
        return True

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


def test_play_async_does_not_pass_explicit_enhance(monkeypatch):
    """Play must NOT pass an explicit enhance kwarg — leaving it at
    speak()'s enhance=None default is what makes it respect the global
    Enhanced toggle (whatever state.enhance_strategy currently is)."""
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


def test_select_enhance_strategy_updates_state_and_persists(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    persisted: list[dict] = []
    monkeypatch.setattr(
        "src.control.app_controller.save_user_override",
        lambda patch, **kw: persisted.append(dict(patch)),
    )

    ctrl.select_enhance_strategy("heuristic")

    assert ctrl.state.enhance_strategy == "heuristic"
    assert persisted[-1]["enhance_strategy"] == "heuristic"


def test_speak_locked_none_enhance_resolves_to_global_toggle(monkeypatch):
    """This is what makes the toggle 'global' — Play, the hotkey, and the
    tray all call speak() with enhance=None, and _speak_locked resolves
    that against AppState.enhance_strategy at call time."""
    ctrl = _make_controller(monkeypatch)
    ctrl.state.set_enhance_strategy("heuristic")
    ctrl.engine = None  # skip the actual engine.speak() call path
    events: list[dict] = []
    monkeypatch.setattr(ctrl.telemetry, "emit", lambda event, **kw: events.append(kw))

    ctrl._speak_locked("foo  bar", None)

    triggered = events[0]
    assert triggered["enhance_strategy"] == "heuristic"
    assert triggered["enhanced_chars"] == len("foo bar.")


def test_speak_locked_explicit_none_overrides_global_toggle(monkeypatch):
    """play_sample_async passes enhance='none' explicitly — that must
    win over the global toggle even when it's on, since the toggle-off
    case is the whole point of an explicit override."""
    ctrl = _make_controller(monkeypatch)
    ctrl.state.set_enhance_strategy("heuristic")
    ctrl.engine = None
    events: list[dict] = []
    monkeypatch.setattr(ctrl.telemetry, "emit", lambda event, **kw: events.append(kw))

    ctrl._speak_locked("foo  bar", "none")

    triggered = events[0]
    assert "enhance_strategy" not in triggered


def test_apply_current_enhance_uses_global_toggle(monkeypatch):
    """Used by the export path — Export must speak whatever text Play
    would speak, so it reads the same global toggle."""
    ctrl = _make_controller(monkeypatch)
    assert ctrl.apply_current_enhance("foo  bar") == "foo  bar"  # toggle off by default

    ctrl.select_enhance_strategy("heuristic")
    assert ctrl.apply_current_enhance("foo  bar") == "foo bar."


def test_export_default_name_includes_session_play_stack_voice(monkeypatch):
    ctrl = _make_controller(monkeypatch)  # active: ml/kokoro, voice: af_heart

    name = ctrl.export_default_name()

    parts = name.split("_")
    assert ctrl.telemetry.session_id in name
    assert "ml" in parts
    assert "af" in parts and "heart" in parts  # af_heart itself contains "_"
    # Two calls must produce different play_ids (uniqueness per export)
    assert ctrl.export_default_name() != name


def test_export_default_name_sanitizes_unsafe_characters(monkeypatch):
    ctrl = _make_controller(
        monkeypatch, cfg=_cfg(engine="ml", model="kokoro", voice="weird:voice/name"),
    )
    name = ctrl.export_default_name()
    assert ":" not in name
    assert "/" not in name


def test_play_sample_async_speaks_fixed_sample_text_always_unenhanced(monkeypatch):
    """Play Sample ignores editor content entirely — it always speaks
    SAMPLE_TEXT with the active voice, restart=True (interrupts anything
    currently playing), and stays unenhanced regardless of the global
    toggle (fixed diagnostic phrase, testing/perf must stay deterministic)."""
    from src.control.app_controller import SAMPLE_TEXT
    ctrl = _make_controller(monkeypatch)
    ctrl.state.set_enhance_strategy("heuristic")  # toggle ON — must still be ignored
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
    assert kwargs.get("enhance") == "none"


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


def test_set_voice_enabled_updates_state_and_persists(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    persisted: list[dict] = []
    monkeypatch.setattr(
        "src.control.app_controller.save_user_override",
        lambda patch, **kw: persisted.append(dict(patch)),
    )

    ctrl.set_voice_enabled("ml", "kokoro", "af_heart", False)

    assert ctrl.state.is_voice_enabled("ml", "kokoro", "af_heart") is False
    assert persisted[-1]["disabled_voices"] == ["ml|kokoro|af_heart"]


def test_preview_voice_reuses_active_engine_when_matching(monkeypatch):
    """Previewing the currently active stack/model must not load a
    redundant second engine instance — it should speak through the
    engine AppController already has."""
    ctrl = _make_controller(monkeypatch)  # active: ml/kokoro
    active_engine = ctrl.engine

    ctrl._preview_voice("ml", "kokoro", "af_heart")

    assert active_engine.spoken == [(_SAMPLE_TEXT_FOR_TEST, "af_heart")]
    assert active_engine.stopped is False  # reused, not torn down
    assert ctrl._load_calls == [("ml", "kokoro")]  # no extra load


def test_preview_voice_loads_and_discards_temp_engine_for_non_active_target(monkeypatch):
    ctrl = _make_controller(monkeypatch)  # active: ml/kokoro
    active_engine = ctrl.engine

    ctrl._preview_voice("ml", "chatterbox", "default")

    assert ctrl.engine is active_engine  # AppController's own engine untouched
    assert ctrl._load_calls == [("ml", "kokoro"), ("ml", "chatterbox")]


def test_preview_voice_emits_telemetry(monkeypatch):
    """Regression test: the Manage Voices dialog's per-row "Try Voice"
    button used to call engine.speak() directly, bypassing telemetry
    entirely — a user in --debug mode got zero events for preview clicks
    while getting full events for the normal Play/hotkey path. Both must
    now go through the same _run_engine_speak() helper and emit the same
    event shape, distinguished only by source="preview" vs source="speak"."""
    ctrl = _make_controller(monkeypatch)  # active: ml/kokoro
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ctrl.telemetry, "emit",
        lambda event, **kw: events.append((event, kw)),
    )

    ctrl._preview_voice("ml", "kokoro", "af_heart")

    event_names = [name for name, _ in events]
    assert "speak.triggered" in event_names
    assert "tts.first_audio" in event_names
    assert "tts.playback_end" in event_names
    assert "speak.done" in event_names
    assert all(kw.get("source") == "preview" for _, kw in events)

    triggered_kw = dict(events[event_names.index("speak.triggered")][1])
    assert triggered_kw["engine"] == "ml"
    assert triggered_kw["model"] == "kokoro"
    assert triggered_kw["voice"] == "af_heart"


def test_speak_locked_text_chars_is_original_not_enhanced_when_engine_present(monkeypatch):
    """Regression test: a prior refactor of _speak_locked into a shared
    _run_engine_speak() helper accidentally computed text_chars/text_bytes
    from the post-enhancement text instead of the original — invisible in
    every other test here because they all set ctrl.engine = None, which
    skips _run_engine_speak entirely and takes a different code path that
    never had the bug. This test keeps the (fake) engine active specifically
    to exercise the path that broke."""
    ctrl = _make_controller(monkeypatch)  # engine stays the real fake, not None
    ctrl.state.set_enhance_strategy("heuristic")
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ctrl.telemetry, "emit",
        lambda event, **kw: events.append((event, kw)),
    )

    raw = "foo   bar"  # heuristic_enhance -> "foo bar." (9 chars -> 8, distinct lengths)
    ctrl._speak_locked(raw, None)

    triggered_kw = dict(events[[n for n, _ in events].index("speak.triggered")][1])
    assert triggered_kw["text_chars"] == len(raw)
    assert triggered_kw["text_bytes"] == len(raw.encode())
    assert triggered_kw["enhanced_chars"] == len("foo bar.")
    assert triggered_kw["text_chars"] != triggered_kw["enhanced_chars"]


def test_preview_voice_text_chars_matches_sample_text(monkeypatch):
    ctrl = _make_controller(monkeypatch)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ctrl.telemetry, "emit",
        lambda event, **kw: events.append((event, kw)),
    )

    ctrl._preview_voice("ml", "kokoro", "af_heart")

    triggered_kw = dict(events[[n for n, _ in events].index("speak.triggered")][1])
    assert triggered_kw["text_chars"] == len(_SAMPLE_TEXT_FOR_TEST)
    assert triggered_kw["text_bytes"] == len(_SAMPLE_TEXT_FOR_TEST.encode())


def test_speak_and_preview_use_distinct_telemetry_source(monkeypatch):
    """The normal speak path and the preview path must be distinguishable
    in the JSONL sink (source field), not just present-or-absent."""
    ctrl = _make_controller(monkeypatch)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ctrl.telemetry, "emit",
        lambda event, **kw: events.append((event, kw)),
    )

    ctrl._speak_locked("hello world", "none")
    ctrl._preview_voice("ml", "kokoro", "af_heart")

    sources = {kw.get("source") for _, kw in events if "source" in kw}
    assert sources == {"speak", "preview"}


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


def test_enhance_text_llm_strategy_falls_back_to_heuristic_on_failure(monkeypatch):
    """Whenever llm_enhance raises (model load failure, output failed
    validation, ...), the Controller must fall back to heuristic rather
    than propagating the failure or silently returning unenhanced text.
    llm_enhance itself is mocked here — its real behavior (including the
    real model) is covered by tests/test_text_enhancer.py."""
    import src.control.app_controller as ac
    monkeypatch.setattr(
        ac.text_enhancer, "llm_enhance",
        lambda text, prompt_path=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ctrl = _make_controller(monkeypatch)
    text, used = ctrl._enhance_text("foo  bar", "llm")
    assert text == "foo bar."
    assert used == "llm_fallback_heuristic"


def test_enhance_text_llm_strategy_uses_result_on_success(monkeypatch):
    import src.control.app_controller as ac
    monkeypatch.setattr(ac.text_enhancer, "llm_enhance", lambda text, prompt_path=None: "Foo, bar.")
    ctrl = _make_controller(monkeypatch)
    text, used = ctrl._enhance_text("foo  bar", "llm")
    assert text == "Foo, bar."
    assert used == "llm"
