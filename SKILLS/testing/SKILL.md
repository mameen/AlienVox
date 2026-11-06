---
name: testing
description: Testing standards for AlienVox. Enforces 80% coverage minimum, no mocking, real fixture files, and pytest as the framework. Applies to python_app and any future implementation.
license: Apache-2.0
compatibility: Python 3.11+, pytest, pytest-cov
metadata:
  author: AlienTech.Software
  version: "1.0"
---

# Testing Standards

## 1. Coverage Requirement

- **Minimum 80% line coverage** across `src/`. This is a hard floor, not a target.
- Measure with `pytest --cov=src --cov-report=term-missing`. Fail the run if coverage drops below 80%.
- Coverage is measured on real code paths, not on test utilities or fixture loaders.

---

## 2. No Mocking

- **Do not mock internal modules, classes, or functions.** If two modules must work together, test them together.
- The only acceptable mock-like boundary is at the **OS/hardware edge**: you may stub `sounddevice.play` or the COM `SAPI.SpVoice` object in tests that would otherwise require audio hardware or a specific Windows environment. These stubs must be explicitly scoped to the test module and never shared as a global patch.
- **Never mock the config system, the engine registry, or the telemetry sink.** Tests that exercise those paths must use real instances.

---

## 2.1 Device Testing — CPU Default, GPU Runs For Real When Present

CPU is the default runtime device (`run.py`'s `_resolve_device()`); GPU is opt-in via `--gpu`/
`--cuda`. Tests must mirror this, not hardcode a device string:

- Never write `.to("cuda")` or `torch_dtype=torch.bfloat16` unconditionally in a test or in engine
  code reached by a test — always go through the same `select_device()` (`src/device.py`) the app
  itself uses, so a test exercises the actual resolution logic, not a stand-in for it.
- GPU-only test paths are marked `@requires_gpu` (`tests/conftest.py`) — this **skips** on a
  CPU-only machine, but on a machine with a real CUDA GPU it **runs for real**, against the actual
  device, not a mocked `torch.cuda.is_available()`. Do not assume your dev/CI machine is CPU-only
  and write GPU code paths that only get theoretical coverage — if a GPU is present, the test suite
  must actually prove the GPU path works, because it will run there.
- This matters concretely, not just in theory: VibeVoice's engine (`vibevoice_engine.py`) shipped
  with two real device-placement bugs — a hardcoded `flash_attention_2` attention implementation
  that isn't installed by default, and a cached KV-prompt loaded via `map_location="cpu"` never
  moved to the model's actual device — that were **invisible on a CPU-only run** and only surfaced
  once the real test suite ran on a machine with an actual GPU (`@requires_gpu` picked it up
  automatically, no test code changes needed to catch it). Assuming "CPU works, therefore GPU
  probably works too" is exactly the gap that produced two separate `RuntimeError`s in production
  code that had already passed CPU testing.

## 2.2 Root-Cause Investigation & Sweep for Similar Instances

When a bug is reported (by the user hearing/seeing it, a failing test, or a crash), don't stop at
the first plausible-looking fix — two separate steps, always:

1. **Find the actual root cause, not the nearest symptom.** "The audio sounded cut short" could be
   the model generating too little audio, `apply_volume()` zeroing it out, a truncated buffer, or
   playback ending early — these have completely different fixes. Trace the real data (buffer
   length vs. reported audio duration, timing logs, etc.) before writing a fix, the same way
   `docs/issues/issue_001.md`/`issue_002.md`'s investigations did — each fix in those was reached
   by chasing a *specific* error message or a *specific* measured discrepancy, never a guess.
2. **Before considering the fix complete, check whether the same class of bug exists anywhere
   else with the same shape.** Concretely: when `audio_player.py`'s `play_audio()` was found to
   clip the tail end of long real synthesis output (`sd.wait()` returns once samples are handed to
   the OS mixer, not once the hardware has actually finished rendering them — a real, audible bug,
   not hypothesized), the right next question wasn't "is this fixed for VibeVoice" but "does every
   other engine's playback path go through this same function, or does one of them call
   `sounddevice` directly and need its own fix?" (Answer, verified by grep: every ML engine —
   Kokoro, Piper, Chatterbox, Dia, F5-TTS, OuteTTS, VibeVoice — routes through the same shared
   `play_audio()`, so the one fix covered all seven; if even one had bypassed it with its own
   `sd.play()` call, that one would still be broken.) A fix that only addresses the specific
   instance that got reported, while leaving three duplicated copies of the same bug untouched
   elsewhere in the codebase, is an incomplete fix.

This is also why the "Adding a New Local ML Engine" checklist (`highlevel_design/SKILL.md` §4.5)
insists on routing every engine through shared helpers (`audio_player.py`, `device.py`,
`models_root()`) rather than each engine reimplementing its own version — a shared helper means a
bug found in one place, fixed in one place, is fixed everywhere; duplicated logic means every
future bug-sweep has to re-check every copy by hand.

---

## 3. Test Data — Fixtures over Mimics

- Use **real YAML fixture files** for config tests, stored under `tests/fixtures/`. These are genuine, valid config files (not artificially constructed dicts) and may be reused across tests.
- Use **real audio WAV files** (under `tests/fixtures/audio/`) when a test must verify audio output. Never generate synthetic sine waves as a substitute for real model output — that tests the wrong thing.
- When a test needs a model that downloads weights, skip it with `pytest.mark.skipif` unless the weights are already present locally. Never download weights inside a test run.
- **No fabricated return values** standing in for real computations. If the computation is expensive, cache it via a session-scoped pytest fixture — run it once, reuse across tests.

---

## 4. Test Structure

```
python_app/
└── tests/
    ├── conftest.py            # Session-scoped fixtures (app instance, config root, etc.)
    ├── fixtures/
    │   ├── models/            # Minimal YAML stacks for config resolution tests
    │   │   ├── sapi5/
    │   │   │   └── stack.yaml
    │   │   └── ml/
    │   │       ├── stack.yaml
    │   │       └── kokoro/
    │   │           └── model.yaml
    │   └── user.yaml          # Sample user overrides
    ├── test_config.py         # 4-layer YAML resolver
    ├── test_telemetry.py      # Event emission and JSONL sink
    ├── test_registry.py       # Stack discovery and availability
    ├── test_capture.py        # Text capture (Windows-only, skipped on other platforms)
    └── test_engines_sapi.py   # SAPI5 engine (Windows-only, COM edge stubbed)
```

---

## 5. Pytest Configuration

Add to `pyproject.toml` or `pytest.ini`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=80"
```

---

## 6. What Each Test Must Prove

Every test must prove **behavior**, not implementation. Ask: "If I refactored the internals completely, would this test still be meaningful?" If yes, keep it. If it only works because it knows the internal variable name, rewrite it.

---

## 7. Canonical Sample Phrase

All ML engines must use the same canonical sample phrase for voice samples and performance tests. This ensures consistent, comparable results across all engines.

**Source:** `python_app/src/control/app_controller.py` — `SAMPLE_TEXT`

```
Welcome to AlienVox. This is a performance test of your TTS engine. If you can hear this, your system is working correctly.
```

**Rules:**
- All offline voice samples in `install/assets/audio/ml/<model>/` must use this exact phrase.
- This remains the English canonical sample (`WELCOME_PHRASE`); the all-voice
  performance sweep uses locale-matched samples from the catalog in Section 10.
- Never use arbitrary text (like "quick brown fox") for voice samples — always use the canonical phrase.
- When generating new voice samples, reference `app_controller.py`'s `SAMPLE_TEXT`, not a hardcoded string in your generation script.

- Config tests: verify the merged output values, not which internal dict was accessed.
- Telemetry tests: verify the JSONL line was written with the correct fields, not that a specific method was called.
- Registry tests: verify which stacks are returned given a specific `.models/` directory layout.
- Engine tests: verify the engine produces a voice list and handles stop without throwing.

## 8. AlienVox Test Commands

Run commands from `python_app` with its virtual environment active. On Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The default pytest run applies the configured 80% coverage floor and excludes
`tests/test_perf.py`. Keep real synthesis benchmarks out of the default suite:
they load local model weights, take much longer than unit tests, and produce
machine-specific measurements.

Run the instrumentation-only performance tests separately:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_perf.py --no-cov -v
```

Run the full welcome-phrase sweep through the task runner when you want all
available voices, including Windows SAPI voices. CPU is the default; specify
`--cpu` to make the intent explicit:

```powershell
.\.venv\Scripts\python.exe run.py perf --cpu
```

For the ML-model-only CPU benchmark, covering every voice for every model with
weights already installed, run:

```powershell
.\.venv\Scripts\python.exe -m tests.test_perf_cpu_models
```

This opt-in runner disables CUDA in its `main()` before model engines load. It
does not download missing weights; unavailable models are reported as skipped.
The sweep writes JSON and HTML reports under `python_app/.logs/`. Do not run it
unless the user asks to benchmark: a full voice sweep is lengthy and consumes
CPU and memory. For one case, use:

```powershell
python run.py perf --cpu --stack ml --model <model-id> --voice <voice-id>
```

## 9. Voice-Quality Ratings and Error Reports

The generated HTML performance report has five clickable stars per voice and
an `!` error flag. Stars are a subjective 1-to-5 listening score, not an
automated quality metric or speed score. Selecting the error flag clears that
voice's star score and disables its stars until the error flag is cleared.

The browser stores ratings and error flags in local storage under a key tied
to that report's timestamp. Use **Download metrics + ratings JSON** in the
report to preserve the results. The export contains `voice_ratings`,
`voice_errors`, and per-result `user_rating_1_to_5` and `error_reported` fields.
Keep the downloaded export with its matching report when sharing or updating
`python_app/docs/performance_voice_preferences.md`; the base benchmark JSON
does not contain browser ratings added later.

## 10. Multilingual Performance Phrases and Voice Preferences

`python_app/tests/fixtures/performance_phrases.json` is the source for localized
performance samples. It currently has 32 locales and four delivery variants:
`neutral`, `warm`, `upbeat`, and `calm`. The benchmark selects a phrase for
each voice's locale, with a conservative language or English fallback. Phrase
translations are marked `pending_native_review`; do not describe them as
native-reviewed. When comparing timings, compare voices using the same phrase
locale because translated phrase lengths differ.

Keep these two sample uses distinct:

- Bundled offline voice samples follow the canonical English `SAMPLE_TEXT` in
  Section 7.
- The performance benchmark uses the locale-matched phrase catalog above.

Developer listening preferences and rated voice shortlists live in
[`python_app/docs/performance_voice_preferences.md`](../../python_app/docs/performance_voice_preferences.md).
Treat them as subjective audition guidance, not objective model rankings. The
developer currently prefers Supertonic 3's voice quality over Piper; Piper was
selected as the CPU trial default for performance/resource reasons, not because
it received a higher quality preference. Preserve the historical numeric
ratings as snapshots and add newer listening notes separately. Read the report
resource caveats in that document before drawing CPU-speed or memory claims.

## 11. Report Examples and Generators

Use the checked-in reports under `references/` as concrete layout and
interaction examples:

- `references/full.html` is the full performance report. Its data is loaded
  from sibling `references/full.js`; `references/full.json` is the raw result
  export. Keep those basenames together because the HTML loads `full.js` by a
  relative path.
- `references/favorite.html` is the CPU comparison for preferred voices.
  `references/favorite.json` is the benchmark input, and the adjacent WAV files
  are the audio samples linked by the report.

The full report is generated by `python_app/tests/test_perf.py` through
`generate_reports()`; its HTML and JSON/JS writers define the current format.
The preferred-voice report renderer is available here:

```powershell
python SKILLS\testing\scripts\render_favorite_report.py `
  SKILLS\testing\references\favorite.json `
  --output SKILLS\testing\references\favorite.html
```

The renderer expects the audio files beside the output HTML. When changing a
report, preserve the JSON data, report-relative asset paths, ratings/error
controls, and measurement caveats. Treat these files as examples; do not edit
the historical reports to represent a new run. Generate new timestamped
reports for new measurements.
