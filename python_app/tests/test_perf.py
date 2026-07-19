"""Instrumentation / performance benchmarks.

These tests assert timing contracts — they do NOT require audio hardware,
a Qt display, or network access. All timings are measured against the real
implementation running on the local machine.

Thresholds are generous to survive slow CI machines (10× headroom over a
typical dev machine). If a threshold is hit in practice, the code is slow.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed_ms(fn, *args, **kwargs) -> float:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000


# ── Config benchmarks ─────────────────────────────────────────────────────────

class TestConfigPerf:
    def test_load_stacks_catalog_under_20ms(self):
        from src.config import load_stacks_catalog
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(load_stacks_catalog, stacks_yaml)
        print(f"\n  load_stacks_catalog: {ms:.2f} ms")
        assert ms < 20, f"load_stacks_catalog took {ms:.1f} ms (threshold 20 ms)"

    def test_list_stacks_under_20ms(self):
        from src.config import list_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(list_stacks, stacks_yaml)
        print(f"\n  list_stacks: {ms:.2f} ms")
        assert ms < 20, f"list_stacks took {ms:.1f} ms (threshold 20 ms)"

    def test_load_effective_config_under_30ms(self, tmp_path):
        from src.config import load_effective_config
        stacks_yaml = FIXTURES / "stacks.yaml"
        user_yaml = tmp_path / "user.yaml"
        ms = _elapsed_ms(load_effective_config, "sapi5", stacks_file=stacks_yaml, user_file=user_yaml)
        print(f"\n  load_effective_config: {ms:.2f} ms")
        assert ms < 30, f"load_effective_config took {ms:.1f} ms (threshold 30 ms)"

    def test_get_controls_under_10ms(self):
        from src.config import get_controls
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(get_controls, "sapi5", stacks_yaml=stacks_yaml)
        print(f"\n  get_controls: {ms:.2f} ms")
        assert ms < 10, f"get_controls took {ms:.1f} ms (threshold 10 ms)"


# ── Registry benchmarks ───────────────────────────────────────────────────────

class TestRegistryPerf:
    def test_available_stacks_under_50ms(self, tmp_path):
        from src.engines.registry import available_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(available_stacks, stacks_yaml, tmp_path)
        print(f"\n  available_stacks (no weights): {ms:.2f} ms")
        assert ms < 50, f"available_stacks took {ms:.1f} ms (threshold 50 ms)"

    def test_available_stacks_with_weights_under_50ms(self, tmp_path):
        from src.engines.registry import available_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        (tmp_path / "ml" / "kokoro").mkdir(parents=True)
        (tmp_path / "ml" / "piper").mkdir(parents=True)
        ms = _elapsed_ms(available_stacks, stacks_yaml, tmp_path)
        print(f"\n  available_stacks (with weights): {ms:.2f} ms")
        assert ms < 50, f"available_stacks took {ms:.1f} ms (threshold 50 ms)"


# ── Telemetry benchmarks ──────────────────────────────────────────────────────

class TestTelemetryPerf:
    def test_emit_single_event_under_5ms(self, tmp_path):
        from src.telemetry import Telemetry
        tel = Telemetry(sink=tmp_path / "tel.jsonl")
        ms = _elapsed_ms(tel.emit, "speak_start", engine="sapi5", text_chars=100)
        print(f"\n  telemetry.emit (single): {ms:.2f} ms")
        assert ms < 5, f"telemetry.emit took {ms:.1f} ms (threshold 5 ms)"

    def test_emit_100_events_under_200ms(self, tmp_path):
        from src.telemetry import Telemetry
        tel = Telemetry(sink=tmp_path / "tel.jsonl")
        t0 = time.perf_counter()
        for i in range(100):
            tel.emit("speak_start", engine="sapi5", text_chars=i)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n  telemetry.emit x100: {ms:.2f} ms ({ms/100:.3f} ms/event)")
        assert ms < 200, f"100 telemetry events took {ms:.1f} ms (threshold 200 ms)"

    def test_jsonl_file_is_valid_json_per_line(self, tmp_path):
        from src.telemetry import Telemetry
        sink = tmp_path / "tel.jsonl"
        tel = Telemetry(sink=sink)
        for i in range(5):
            tel.emit("speak_start", engine="sapi5", text_chars=i * 10)
        lines = sink.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for line in lines:
            record = json.loads(line)
            assert "event" in record
            assert "timestamp_unix_ms" in record
            assert "session_id" in record
