"""Explicit CPU-only synthesis sweep across all installed ML voices.

Run from ``python_app`` with its environment active:
    python -m tests.test_perf_cpu_models

This is intentionally an opt-in benchmark, not part of pytest's default suite.
It measures every voice for each installed ML model and writes the standard
JSON/HTML performance report into ``.logs``. Missing model weights are reported
as skipped by the shared benchmark harness.
"""
from __future__ import annotations

import os

from tests.test_perf import (  # noqa: E402
    generate_reports,
    render_console_table,
    welcome_phrase_benchmark,
)


def main() -> int:
    # Set this before the benchmark loads any engine or model implementation.
    # Keeping it inside main() avoids changing pytest's environment at collection.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    print("CPU-only benchmark: all installed ML models and voices")
    results = welcome_phrase_benchmark(ml_only=True)
    render_console_table(results)
    json_path, html_path = generate_reports(results)
    print(f"\nJSON report: {json_path}")
    print(f"HTML report: {html_path}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
