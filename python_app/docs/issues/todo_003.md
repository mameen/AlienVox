# TODO #003: Performance Testing Harness

**Status:** Closed — implemented as specified; see 2026-07-22 note.
**Created:** 2026-07-20 · **Closed:** 2026-07-22
**Scope:** `tests/test_perf.py`, `python_app/.logs/`

---

## 2026-07-22 housekeeping note

`tests/test_perf.py` implements every requirement below: `collect_metrics`, `write_json_report`,
`generate_css`/`generate_html`, `write_html_report`, `render_console_table` as separate functions;
timestamped JSON+HTML reports in `.logs/`; color-coded `THRESHOLDS`; SAPI5 enumerated per-voice;
ML engines skipped gracefully when weights are missing. Also gained a capability beyond the
original spec: `python run.py perf --stack <id> --model <id> --voice <id>` for a single-case run
instead of the full sweep (see `run.py`'s `cmd_perf` docstring). Closing rather than leaving open.

---

---

## Goal

`python run.py perf` must run all performance tests, including a **mandatory real-speech benchmark** that speaks a welcome phrase on every available stack/config and collects 4 key metrics.

---

## Requirements

### 1. Welcome Phrase Benchmark (MANDATORY)

- Speak a fixed welcome phrase on **every available stack + model combination**.
- Welcome phrase: `"Welcome to AlienVox. This is a performance test of your TTS engine."`
- For each stack/model, collect these 4 metrics:

| # | Metric | Description | Unit |
|---|--------|-------------|------|
| 1 | **Latency to first voice** | Time from `speak()` call to first audio output | ms |
| 2 | **Memory usage** | RSS (Resident Set Size) before and after speak | MB |
| 3 | **CPU usage** | Peak CPU % during speak | % |
| 4 | **Completion time** | Total time from `speak()` to audio complete | ms |

> GPU metric is included where applicable (ML engines with CUDA).

### 2. Console Output — Formatted ASCII Table

- Display results in a clean, aligned ASCII table in the console.
- Columns: `Stack | Model | Voice | Latency(ms) | Memory(MB) | CPU(%) | Time(ms)`
- Summary row at bottom with averages per metric.
- Color-coded status: green (under threshold), yellow (warning), red (over threshold).

### 3. HTML/JSON Reports in `.logs/`

- Timestamp naming: `YYYYMMDDHHmmss.json` and `YYYYMMDDHHmmss.html`
- Location: `python_app/.logs/`
- **JSON** contains the raw data — all metrics for every stack/model run.
- **HTML** loads the JSON (same name, `.html` extension) and renders an interactive D3 visualization.
- Both files are written atomically (write to temp → rename).

### 4. Code Structure — Separate Reusable Functions

The implementation MUST be split into these separate functions:

| Function | Purpose |
|----------|---------|
| `collect_metrics(phrase, engine, voice_id)` | Run one speak cycle, return dict with all 4 metrics |
| `write_json_report(results, path)` | Write raw results to JSON file |
| `generate_css()` | Generate CSS string for the HTML report |
| `generate_html(json_path)` | Generate HTML string that loads json_path + D3 viz |
| `write_html_report(html_str, path)` | Write HTML to file |
| `render_console_table(results)` | Print formatted ASCII table to console |

**No monolithic function.** Each function is independently testable.

### 5. Thresholds (configurable)

Define thresholds as constants at the top of the file:

```python
THRESHOLDS = {
    "latency_ms":   {"warn": 2000, "error": 5000},
    "memory_mb":    {"warn": 500,  "error": 1000},
    "cpu_percent":  {"warn": 80,   "error": 95},
    "completion_ms":{"warn": 3000, "error": 8000},
}
```

Results are color-coded against these thresholds in both console and HTML.

### 6. ML Engine Handling

- ML engines (Kokoro, Piper, Chatterbox, Dia, F5-TTS, OuteTTS) may not have weights installed.
- **Skip** stacks/models without weights — do NOT fail the test suite.
- Log which stacks were skipped and why.
- For Kokoro with `auto_download: true`, run the benchmark only if weights exist (don't trigger downloads during perf tests).

### 7. SAPI5 Handling

- Run on **every available SAPI5 voice** (enumerate via `engine.list_voices()`).
- Each voice is a separate row in the results.

---

## Implementation Plan

1. Create `tests/test_perf.py` with all functions listed above.
2. Add `welcome_phrase_benchmark()` class that iterates stacks → models → voices.
3. Wire `cmd_perf()` in `run.py` to call the benchmark + existing unit benchmarks.
4. Create `.logs/` directory if it doesn't exist.
5. Ensure pytest can run `python run.py perf` without Qt display or audio hardware for the unit benchmarks, and gracefully handles missing hardware for the speech benchmark.

---

## Notes

- Memory: use `psutil.Process().memory_info().rss` (add to requirements if not present).
- CPU: use `psutil.Process().cpu_percent(interval=None)` with delta calculation.
- GPU: use `nvidia-ml-py` if available, else skip silently.
- Latency to first voice: for SAPI5 this is time to COM submit; for ML engines it's time to first audio sample generation. Approximate via `speak()` → first callback/timestamp.
- Completion time: use `engine.wait_until_done(timeout_ms=30000)` or engine-specific completion signal.
