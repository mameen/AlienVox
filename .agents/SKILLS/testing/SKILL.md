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

- Config tests: verify the merged output values, not which internal dict was accessed.
- Telemetry tests: verify the JSONL line was written with the correct fields, not that a specific method was called.
- Registry tests: verify which stacks are returned given a specific `.models/` directory layout.
- Engine tests: verify the engine produces a voice list and handles stop without throwing.
