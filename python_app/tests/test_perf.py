"""Performance testing harness for AlienVox.

Mandatory welcome-phrase benchmark + unit-level instrumentation benchmarks.

Usage:
    python run.py perf          # runs all perf tests via pytest
    python run.py perf --real   # runs real-speech benchmark (requires audio)

Metrics collected per stack/model/voice:
    1. latency_ms      — time from speak() to first audio output
    2. memory_mb       — RSS delta before/after speak
    3. cpu_percent     — peak CPU during speak
    4. completion_ms   — total time from speak() to audio complete

Reports written to .logs/YYYYMMDDHHmmss.{json,html}
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

# ── Thresholds ────────────────────────────────────────────────────────────────

THRESHOLDS = {
    "latency_ms":   {"warn": 2000, "error": 5000},
    "memory_mb":    {"warn": 500,  "error": 1000},
    "cpu_percent":  {"warn": 80,   "error": 95},
    "completion_ms":{"warn": 3000, "error": 8000},
}

# ── Welcome phrase (mandatory) ────────────────────────────────────────────────

WELCOME_PHRASE = (
    "Welcome to AlienVox. This is a performance test of your TTS engine. "
    "If you can hear this, your system is working correctly."
)

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
LOGS_DIR = ROOT / ".logs"

# ── psutil helpers (optional — skip if not installed) ─────────────────────────

_psutil_available = False
try:
    import psutil  # type: ignore
    _psutil_available = True
except ImportError:
    pass


def _get_memory_mb() -> float:
    """Return current process RSS in MB."""
    if not _psutil_available:
        return -1.0
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024 * 1024)


def _get_cpu_percent() -> float:
    """Return current process CPU % (non-blocking)."""
    if not _psutil_available:
        return -1.0
    return psutil.Process(os.getpid()).cpu_percent(interval=None)


# ── Status coloring ───────────────────────────────────────────────────────────

def _status_color(value: float, metric: str) -> str:
    """Return ANSI color code based on thresholds."""
    if value < 0:
        return "\033[90m"  # grey (N/A)
    thresh = THRESHOLDS.get(metric, {})
    if value >= thresh.get("error", float("inf")):
        return "\033[91m"  # red
    if value >= thresh.get("warn", float("inf")):
        return "\033[93m"  # yellow
    return "\033[92m"    # green


def _reset_color() -> str:
    return "\033[0m"


# ── Metric collection (mandatory) ─────────────────────────────────────────────

@dataclass
class PerfResult:
    stack_id: str
    model_id: str | None = None
    voice_id: str = ""
    latency_ms: float = 0.0
    memory_mb: float = -1.0
    cpu_percent: float = -1.0
    completion_ms: float = 0.0
    gpu_mb: float = -1.0
    skipped: bool = False
    skip_reason: str = ""


def collect_metrics(
    phrase: str,
    engine: Any,
    voice_id: str,
) -> PerfResult:
    """Run one speak cycle and collect all 4 metrics.

    Returns a PerfResult with measured values. Does NOT modify global state.
    """
    result = PerfResult(
        stack_id=getattr(engine, "stack_id", "unknown"),
        model_id=getattr(engine, "model_id", None),
        voice_id=voice_id,
    )

    if not _psutil_available:
        result.skipped = True
        result.skip_reason = "psutil not installed"
        return result

    # ── Memory baseline ───────────────────────────────────────────────────
    mem_before = _get_memory_mb()
    cpu_start = _get_cpu_percent()

    # ── Latency to first audio ────────────────────────────────────────────
    from src.engines.base import SpeakParams

    latency_start = time.perf_counter()

    # ── Completion tracking ───────────────────────────────────────────────
    completion_start = time.perf_counter()
    try:
        engine.speak(phrase, voice_id, SpeakParams())
    except Exception as exc:
        result.skipped = True
        result.skip_reason = f"speak() failed: {exc}"
        return result

    # Wait for SAPI completion or ML engine signal
    done = engine.wait_until_done(timeout_ms=30_000)
    completion_end = time.perf_counter()

    # ── Compute metrics ───────────────────────────────────────────────────
    result.latency_ms = (time.perf_counter() - latency_start) * 1000
    result.completion_ms = (completion_end - completion_start) * 1000
    result.memory_mb = _get_memory_mb() - mem_before
    result.cpu_percent = max(0, _get_cpu_percent() - cpu_start)

    # ── GPU metric (optional) ─────────────────────────────────────────────
    try:
        import pynvml  # type: ignore
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        result.gpu_mb = mem_info.used / (1024 * 1024)
        pynvml.nvmlShutdown()
    except Exception:
        result.gpu_mb = -1.0

    return result


# ── Welcome phrase benchmark ──────────────────────────────────────────────────

def welcome_phrase_benchmark() -> list[PerfResult]:
    """Speak WELCOME_PHRASE on every available stack/model/voice combination.

    Returns a list of PerfResults. Skips unavailable stacks/models gracefully.
    """
    results: list[PerfResult] = []
    skipped: list[str] = []

    from src.config import load_stacks_catalog, list_stacks
    from src.engines.registry import available_stacks

    stacks_yaml = FIXTURES / "stacks.yaml"
    models_root = ROOT  # dev mode: .models/ next to stacks.yaml

    # Load stack catalog
    catalog = load_stacks_catalog(stacks_yaml)
    stack_ids = list_stacks(stacks_yaml)

    for stack_id in stack_ids:
        # ── SAPI5 / Speech Platform (enumerate voices via engine) ─────────
        if stack_id in ("sapi5", "speech_platform"):
            try:
                if sys.platform != "win32":
                    skipped.append(f"{stack_id}: not on Windows")
                    continue

                from src.engines.sapi_win import SapiEngine
                engine = SapiEngine()
                engine.stack_id = stack_id  # set for perf reporting
                voices = engine.list_voices()

                if not voices:
                    skipped.append(f"{stack_id}: no voices found")
                    continue

                for voice in voices:
                    r = collect_metrics(WELCOME_PHRASE, engine, voice.id)
                    # Truncate registry path to last segment for display
                    r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
                    results.append(r)

            except Exception as exc:
                skipped.append(f"{stack_id}: {exc}")
            continue

        # ── ML stacks (iterate models) ────────────────────────────────────
        stack_info = available_stacks(stacks_yaml, models_root)
        stack_entry = None
        for s in stack_info:
            if s.id == stack_id and s.models:
                stack_entry = s
                break

        if not stack_entry:
            skipped.append(f"{stack_id}: no models in catalog")
            continue

        for model in stack_entry.models:
            if not model.available:
                skipped.append(f"{stack_id}/{model.id}: weights not installed")
                continue

            # ── Try to load the engine ────────────────────────────────────
            try:
                engine = _load_ml_engine(stack_id, model)
                if engine is None:
                    skipped.append(f"{stack_id}/{model.id}: engine load failed")
                    continue

                # Set stack_id and model_id for perf reporting
                engine.stack_id = stack_id
                engine.model_id = model.id

                voices = engine.list_voices()
                for voice in voices:
                    r = collect_metrics(WELCOME_PHRASE, engine, voice.id)
                    # Truncate registry path to last segment for display
                    r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
                    results.append(r)

            except Exception as exc:
                skipped.append(f"{stack_id}/{model.id}: {exc}")

    # Print skipped stacks
    if skipped:
        print("\n  Skipped:")
        for s in skipped:
            print(f"    ⏭ {s}")

    return results


def _load_ml_engine(stack_id: str, model_info: Any) -> Any | None:
    """Load an ML engine instance. Returns None on failure."""
    try:
        model_id = model_info.id
        if model_id == "kokoro":
            from src.engines.kokoro_engine import KokoroEngine
            return KokoroEngine()
        elif model_id == "piper":
            from src.engines.piper_win import PiperEngine
            return PiperEngine(model_id)
        elif model_id == "chatterbox":
            from src.engines.chatterbox_engine import ChatterboxEngine
            return ChatterboxEngine()
        elif model_id == "dia":
            from src.engines.dia_engine import DiaEngine
            return DiaEngine()
        elif model_id == "f5tts":
            from src.engines.f5tts_engine import F5TTSEngine
            return F5TTSEngine()
        elif model_id == "outetts":
            from src.engines.outetts_engine import OuteTTSEngine
            return OuteTTSEngine()
    except Exception:
        pass
    return None


# ── Console table rendering ───────────────────────────────────────────────────

def render_console_table(results: list[PerfResult]) -> None:
    """Print formatted ASCII table to console with color-coded thresholds."""
    if not results:
        print("\n  No results to display.")
        return

    # Column widths
    col_w = {
        "stack": max(8, max(len(r.stack_id) for r in results)),
        "model": max(6, max(len(r.model_id or "-") for r in results)),
        "voice": max(5, max(len(r.voice_id) for r in results)),
    }
    col_w["lat"] = 10
    col_w["mem"] = 9
    col_w["cpu"] = 7
    col_w["comp"] = 10

    header_fmt = (
        f"  {{:<{col_w['stack']}}}  "
        f"{{:<{col_w['model']}}}  "
        f"{{:<{col_w['voice']}}}  "
        f"{{:>{col_w['lat']}}}  "
        f"{{:>{col_w['mem']}}}  "
        f"{{:>{col_w['cpu']}}}  "
        f"{{:>{col_w['comp']}}}"
    )

    total_width = col_w["stack"] + col_w["model"] + col_w["voice"] + col_w["lat"] + col_w["mem"] + col_w["cpu"] + col_w["comp"] + 28
    print(f"\n{'─' * total_width}")
    print(header_fmt.format(
        "STACK", "MODEL", "VOICE",
        "LATENCY(ms)", "MEM(MB)", "CPU(%)", "TIME(ms)"
    ))
    print(f"{'─' * total_width}")

    # Data rows
    for r in results:
        if r.skipped:
            print(f"  {r.stack_id:<{col_w['stack']}}  {r.model_id or '-':<{col_w['model']}}  {r.voice_id:<{col_w['voice']}}  ⏭ {r.skip_reason}")
            continue

        c = _reset_color()
        lat_c = _status_color(r.latency_ms, "latency_ms")
        mem_c = _status_color(r.memory_mb, "memory_mb")
        cpu_c = _status_color(r.cpu_percent, "cpu_percent")
        comp_c = _status_color(r.completion_ms, "completion_ms")

        print(header_fmt.format(
            f"{lat_c}{r.stack_id}{c}",
            f"{mem_c}{r.model_id or '-'}{c}",
            f"{cpu_c}{r.voice_id[:col_w['voice']-1]}{c}",
            f"{comp_c}{r.latency_ms:>7.1f} ms{c}",
            f"  {r.memory_mb:>6.1f} MB",
            f"  {r.cpu_percent:>5.1f} %",
            f"  {r.completion_ms:>7.1f} ms",
        ))

    # Summary row
    valid = [r for r in results if not r.skipped]
    if valid:
        avg_lat = sum(r.latency_ms for r in valid) / len(valid)
        avg_mem = sum(r.memory_mb for r in valid) / len(valid)
        avg_cpu = sum(r.cpu_percent for r in valid) / len(valid)
        avg_comp = sum(r.completion_ms for r in valid) / len(valid)

        print(f"{'─' * total_width}")
        print(header_fmt.format(
            "AVG", "", "",
            f"{avg_lat:>7.1f} ms",
            f"  {avg_mem:>6.1f} MB",
            f"  {avg_cpu:>5.1f} %",
            f"  {avg_comp:>7.1f} ms",
        ))
        print(f"{'─' * total_width}")


# ── JSON report ───────────────────────────────────────────────────────────────

def write_json_report(results: list[PerfResult], path: Path) -> None:
    """Write raw results to JSON file atomically."""
    data = {
        "timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
        "platform": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "welcome_phrase": WELCOME_PHRASE,
        "thresholds": THRESHOLDS,
        "results": [asdict(r) for r in results],
    }

    # Atomic write: temp → rename
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=path.parent, delete=False) as f:
        json.dump(data, f, indent=2, default=str)
        tmp_path = f.name
    shutil.move(tmp_path, path)

    # Also write a JS wrapper so the HTML can <script src> it
    js_path = path.with_suffix(".js")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", dir=path.parent, delete=False) as f:
        f.write(f"const data = {json.dumps(data, indent=2)};")
        tmp_js = f.name
    shutil.move(tmp_js, js_path)


# ── CSS generation ────────────────────────────────────────────────────────────

def generate_css() -> str:
    """Generate CSS string for the HTML report."""
    return """
body {
    font-family: 'Segoe UI', Consolas, monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    margin: 0;
    padding: 20px;
}
h1 { color: #00d4ff; text-align: center; }
h2 { color: #7b68ee; margin-top: 30px; }
#info { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
#chart-container { width: 100%; height: 400px; }
table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #16213e; border-radius: 8px; overflow: hidden; }
th { background: #0f3460; color: #00d4ff; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #1a1a3e; }
tr:hover { background: #1f2b4d; }
.status-ok { color: #00ff88; }
.status-warn { color: #ffaa00; }
.status-error { color: #ff4444; }
.status-na { color: #666; }
.legend { display: flex; gap: 20px; margin-top: 10px; font-size: 14px; }
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; }
"""


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(json_js_path: str) -> str:
    """Generate HTML string that includes data via <script src>."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AlienVox Performance Report</title>
<style>
{generate_css()}
</style>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="{json_js_path}"></script>
</head>
<body>
<h1>AlienVox Performance Report</h1>
<div id="info">Rendering report...</div>
<h2>Metrics by Stack/Model/Voice</h2>
<div id="chart-container"></div>
<h2>Raw Results</h2>
<table id="results-table">
<thead><tr>
    <th>Stack</th><th>Model</th><th>Voice</th>
    <th>Latency (ms)</th><th>Memory (MB)</th><th>CPU (%)</th><th>Time (ms)</th>
</tr></thead>
<tbody id="results-body"></tbody>
</table>

<script>
const THRESHOLDS = {json.dumps(THRESHOLDS, indent=2)};
const WELCOME_PHRASE = {json.dumps(WELCOME_PHRASE)};

d3.run(function() {{
    document.getElementById('info').innerHTML =
        '<b>Generated:</b> ' + data.timestamp + ' | ' +
        '<b>Platform:</b> ' + data.platform.os + ' ' + data.platform.release + ' | ' +
        '<b>Python:</b> ' + data.platform.python + ' | ' +
        '<b>Runs:</b> ' + data.results.length;

    // ── Bar chart: latency & completion time ──
    const container = document.getElementById('chart-container');
    const margin = {{top: 20, right: 30, bottom: 80, left: 60}};
    const width = container.clientWidth - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    const svg = d3.select('#chart-container')
        .append('svg')
        .attr('width', width + margin.left + margin.right)
        .attr('height', height + margin.top + margin.bottom)
        .append('g')
        .attr('transform', `translate(${{margin.left}},${{margin.top}})`);

    const x0 = d3.scaleBand()
        .domain(data.results.map(d => d.stack_id + (d.model_id ? '/' + d.model_id : '')))
        .rangeRound([0, width])
        .paddingInner(0.1);

    const x1 = d3.scaleBand()
        .domain(['latency_ms', 'completion_ms'])
        .range([0, x0.bandwidth()])
        .padding(0.05);

    const y = d3.scaleLinear()
        .domain([0, d3.max(data.results, d => Math.max(d.latency_ms, d.completion_ms)) * 1.1 || 100])
        .nice()
        .range([height, 0]);

    svg.append('g')
        .attr('transform', `translate(0,${{height}})`)
        .call(d3.axisBottom(x0))
        .selectAll('text')
        .attr('transform', 'rotate(-25)')
        .style('text-anchor', 'end');

    svg.append('g').call(d3.axisLeft(y));

    const color = d3.scaleOrdinal()
        .domain(['latency_ms', 'completion_ms'])
        .range(['#00d4ff', '#7b68ee']);

    data.results.forEach(d => {{
        const key = d.stack_id + (d.model_id ? '/' + d.model_id : '');
        svg.append('rect')
            .attr('x', x0(key) + x1('latency_ms'))
            .attr('y', y(d.latency_ms))
            .attr('width', x1.bandwidth())
            .attr('height', height - y(d.latency_ms))
            .attr('fill', color('latency_ms'))
            .attr('rx', 2);

        svg.append('rect')
            .attr('x', x0(key) + x1('completion_ms'))
            .attr('y', y(d.completion_ms))
            .attr('width', x1.bandwidth())
            .attr('height', height - y(d.completion_ms))
            .attr('fill', color('completion_ms'))
            .attr('rx', 2);
    }});

    // ── Legend ──
    const legend = d3.select('#chart-container').append('div').attr('class', 'legend');
    ['latency_ms', 'completion_ms'].forEach(metric => {{
        const item = legend.append('div').attr('class', 'legend-item');
        item.append('div').attr('class', 'legend-dot')
            .style('background', color(metric));
        item.append('span').text(metric.replace('_', ' ').replace(/\\b\\w/g, c => c.toUpperCase()));
    }});

    // ── Table rows ──
    const tbody = document.getElementById('results-body');
    data.results.forEach(d => {{
        const tr = tbody.insertRow();
        ['stack_id','model_id','voice_id','latency_ms','memory_mb','cpu_percent','completion_ms'].forEach(key => {{
            const td = tr.insertCell();
            let val = d[key];
            if (val === -1 || val === null) {{ val = 'N/A'; td.className = 'status-na'; }}
            else if (THRESHOLDS[key] && val >= THRESHOLDS[key].warn) {{ td.className = 'status-warn'; }}
            else if (THRESHOLDS[key] && val >= THRESHOLDS[key].error) {{ td.className = 'status-error'; }}
            else {{ td.className = 'status-ok'; }}
            td.textContent = key.includes('ms') ? val.toFixed(1) + ' ms' :
                             key.includes('mb') ? val.toFixed(1) + ' MB' :
                             key.includes('percent') ? val.toFixed(1) + '%' : val;
        }});
    }});
}}).catch(err => {{
    document.getElementById('info').innerHTML = '<b>Error rendering:</b> ' + err.message;
}});
</script>
</body>
</html>"""


# ── HTML report writer ────────────────────────────────────────────────────────

def write_html_report(html_str: str, path: Path) -> None:
    """Write HTML report to the given path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", dir=path.parent, delete=False, encoding="utf-8") as f:
        f.write(html_str)
        tmp_path = f.name
    shutil.move(tmp_path, path)


# ── Report generation (orchestrator) ──────────────────────────────────────────

def generate_reports(results: list[PerfResult]) -> tuple[Path, Path]:
    """Generate JSON + HTML reports in .logs/ with timestamp naming.

    Returns (json_path, html_path).
    """
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    json_path = LOGS_DIR / f"{ts}.json"
    html_path = LOGS_DIR / f"{ts}.html"

    write_json_report(results, json_path)
    # HTML includes the JS file via <script src>
    js_rel = f"./{ts}.js"
    write_html_report(generate_html(js_rel), html_path)

    return json_path, html_path


# ── Pytest integration (unit benchmarks only — no real-speech) ────────────────

# Real-speech benchmark runs standalone via run.py cmd_perf() because SAPI COM
# requires STA threading, which pytest's test runner does not set up correctly.


# ── Unit-level benchmarks (no audio required) ─────────────────────────────────

class TestConfigPerf:
    """Existing unit benchmarks — timing contracts for config/registry/telemetry."""

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

    def test_get_controls_under_25ms(self):
        from src.config import get_controls
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(get_controls, "sapi5", stacks_yaml=stacks_yaml)
        print(f"\n  get_controls: {ms:.2f} ms")
        assert ms < 25, f"get_controls took {ms:.1f} ms (threshold 25 ms)"


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


# ── Helpers (used by benchmarks) ──────────────────────────────────────────────

def _elapsed_ms(fn, *args, **kwargs) -> float:
    """Measure function execution time in milliseconds."""
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000


# ── CLI entry point (python -m tests.test_perf _benchmark) ───────────────────

if __name__ == "__main__":
    if "_benchmark" in sys.argv:
        print("\n  Running welcome-phrase benchmark on all available stacks/models/voices...\n")
        results = welcome_phrase_benchmark()
        render_console_table(results)
        json_path, html_path = generate_reports(results)
        print(f"\n  JSON report: {json_path}")
        print(f"  HTML report: {html_path}")
        print()
