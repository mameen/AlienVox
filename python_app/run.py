#!/usr/bin/env python3
"""AlienVox task runner.

Usage:
    python run.py app        -- start the application
    python run.py health     -- check imports, version pins, model weights are ready
    python run.py download   -- download missing ML model weights to .models/
    python run.py download --force  -- re-download weights even if already present
    python run.py build      -- syntax-check all src/ files
    python run.py lint       -- run ruff on src/ and tests/
    python run.py test       -- run pytest (with coverage floor)
    python run.py cov        -- run pytest + open HTML coverage report
    python run.py perf       -- run instrumentation benchmarks
    python run.py all        -- lint -> build -> test -> cov -> perf
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
VENV_DIR = ROOT / ".venv"


def _venv_python() -> str:
    """Return venv python executable if it exists, else sys.executable."""
    if sys.platform.startswith("win"):
        exe = VENV_DIR / "Scripts" / "python.exe"
    else:
        exe = VENV_DIR / "bin" / "python"
    return str(exe) if exe.exists() else sys.executable


def _run(*args: str, cwd: Path = ROOT) -> int:
    result = subprocess.run(args, cwd=cwd)
    return result.returncode


def _header(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n┌{bar}┐")
    print(f"│  {title}  │")
    print(f"└{bar}┘")
    sys.stdout.flush()  # ensure this prints before any subprocess output interleaves


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_app() -> int:
    _header("Starting AlienVox")
    # Run as a package module so relative imports work correctly.
    return _run(_venv_python(), "-m", "src.main", cwd=ROOT)


def cmd_health() -> int:
    _header("Health — imports, version pins, model weights")
    return _run(_venv_python(), "-m", "src.health", cwd=ROOT)


def cmd_download() -> int:
    _header("Download — ML model weights")
    extra = sys.argv[2:]  # e.g. --force
    return _run(_venv_python(), str(ROOT / "setup.py"), "download", *extra)


def cmd_build() -> int:
    _header("Build — syntax check")
    import py_compile
    import ast

    failed: list[str] = []
    files = list(SRC.rglob("*.py"))
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as exc:
            print(f"  FAIL  {f.relative_to(ROOT)}: {exc}")
            failed.append(str(f))

    if failed:
        print(f"\n  {len(failed)} file(s) failed to compile.")
        return 1

    print(f"  OK  {len(files)} file(s) compiled without errors.")
    return 0


def cmd_lint() -> int:
    _header("Lint — ruff")
    rc = _run(_venv_python(), "-m", "ruff", "check", str(SRC), str(TESTS))
    if rc != 0:
        print("\n  Hint: run `python -m ruff check --fix src/ tests/` to auto-fix.")
    return rc


def cmd_test() -> int:
    _header("Test — pytest")
    return _run(_venv_python(), "-m", "pytest", str(TESTS), "-v")


def cmd_cov() -> int:
    _header("Coverage — pytest + HTML report")
    rc = _run(
        _venv_python(), "-m", "pytest", str(TESTS),
        "--cov=src",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--cov-fail-under=80",
        "-v",
    )
    html = ROOT / "htmlcov" / "index.html"
    if html.exists():
        import webbrowser
        webbrowser.open(html.as_uri())
    return rc


def cmd_perf() -> int:
    _header("Perf — instrumentation benchmarks")

    # ── Unit benchmarks via pytest (config/registry/telemetry) ─────────────
    rc = _run(
        _venv_python(), "-m", "pytest",
        str(TESTS / "test_perf.py"),
        "-v", "--no-header", "--tb=short",
        "--no-cov",
    )

    # ── Real-speech benchmark (standalone — SAPI COM requires STA threading) ─
    _header("Perf — welcome phrase benchmark")
    rc_perf = _run(
        _venv_python(), "-m", "tests.test_perf", "_benchmark",
    )
    return rc or rc_perf or 0


def cmd_all() -> int:
    _header("All — lint → build → test → cov → perf")
    steps = [
        ("lint",  cmd_lint),
        ("build", cmd_build),
        ("test",  cmd_test),
        ("cov",   cmd_cov),
        ("perf",  cmd_perf),
    ]
    failures: list[str] = []
    for name, fn in steps:
        t0 = time.perf_counter()
        rc = fn()
        elapsed = time.perf_counter() - t0
        status = "OK " if rc == 0 else "FAIL"
        print(f"\n  [{status}] {name}  ({elapsed:.1f}s)")
        if rc != 0:
            failures.append(name)

    print()
    if failures:
        print(f"  Failed steps: {', '.join(failures)}")
        return 1
    print("  All steps passed.")
    return 0


# ── Dispatch ──────────────────────────────────────────────────────────────────

COMMANDS = {
    "app":      cmd_app,
    "health":   cmd_health,
    "download": cmd_download,
    "build":    cmd_build,
    "lint":  cmd_lint,
    "test":  cmd_test,
    "cov":   cmd_cov,
    "perf":  cmd_perf,
    "all":   cmd_all,
}

if __name__ == "__main__":
    # Windows consoles often default to cp1252, which can't encode the
    # box-drawing/em-dash characters used in _header() and subcommand output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)

    sys.exit(COMMANDS[sys.argv[1]]())
