#!/usr/bin/env python3
"""AlienVox task runner.

Usage:
    python run.py app        -- start the application (CPU-only by default)
    python run.py app --gpu  -- use CUDA; fails fast if no GPU is available
                                 (--cuda is an alias for --gpu; respects
                                 CUDA_VISIBLE_DEVICES from .env if set there)
    python run.py app --cpu  -- explicit CPU-only (same as the default; for clarity)
    python run.py app --debug -- also record raw + enhanced text in telemetry
                                 (local .logs/*.jsonl only — never in normal mode)
    python run.py health     -- check imports, version pins, model weights are ready
    python run.py health --cpu / --gpu  -- same device override, for health reporting
    python run.py download   -- download missing ML model weights to .models/
    python run.py download --force  -- re-download weights even if already present
    python run.py build      -- syntax-check all src/ files
    python run.py lint       -- run ruff on src/ and tests/
    python run.py test       -- run pytest (with coverage floor)
    python run.py cov        -- run pytest + open HTML coverage report
    python run.py perf       -- run instrumentation benchmarks (CPU-only by default)
    python run.py perf --cpu / --gpu  -- same device override, for perf comparisons
    python run.py all        -- lint -> build -> test -> cov -> perf

CPU-only is the safe default for app/health/perf — pass --gpu/--cuda to opt
into CUDA. .env (python-dotenv) is always loaded first, so a
CUDA_VISIBLE_DEVICES set there (e.g. to pick a specific card) takes effect
whenever --gpu is used.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
VENV_DIR = ROOT / ".venv"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass  # python-dotenv not installed yet (e.g. before first `python setup.py`)


def _venv_python() -> str:
    """Return venv python executable if it exists, else sys.executable."""
    if sys.platform.startswith("win"):
        exe = VENV_DIR / "Scripts" / "python.exe"
    else:
        exe = VENV_DIR / "bin" / "python"
    return str(exe) if exe.exists() else sys.executable


def _run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> int:
    full_env = {**os.environ, **env} if env else None
    result = subprocess.run(args, cwd=cwd, env=full_env)
    return result.returncode


# ── Device override (--cpu / --gpu / --cuda) ────────────────────────────────
# CPU-only is the default — applies uniformly to every ML engine via
# CUDA_VISIBLE_DEVICES, no per-engine code changes needed, since they already
# call torch.cuda.is_available() internally and that respects this env var.
# --gpu/--cuda opts into CUDA, respecting a CUDA_VISIBLE_DEVICES set in .env
# (e.g. to pick a specific card) since .env is loaded before this runs.

def _parse_device_flag() -> str:
    """Return 'cpu' (default) or 'gpu' from --cpu / --gpu / --cuda in sys.argv."""
    args = set(sys.argv[2:])
    if "--gpu" in args or "--cuda" in args:
        return "gpu"
    return "cpu"  # default, whether or not --cpu was passed explicitly


def _cuda_available(env: dict[str, str] | None = None) -> bool:
    # torch.cuda.is_available() can return True with zero visible devices
    # (e.g. under a forced CUDA_VISIBLE_DEVICES="") — device_count() is the
    # real signal for "is there a GPU to use."
    full_env = {**os.environ, **env} if env else None
    result = subprocess.run(
        [_venv_python(), "-c",
         "import torch, sys; "
         "sys.exit(0 if torch.cuda.is_available() and torch.cuda.device_count() > 0 else 1)"],
        cwd=ROOT, env=full_env,
    )
    return result.returncode == 0


def _resolve_device() -> tuple[dict[str, str], int | None]:
    """Parse --cpu/--gpu, validate, and return (env_overrides, early_exit_code).

    If early_exit_code is not None, the caller should return it immediately
    (used when --gpu/--cuda was requested but no CUDA GPU is present).
    """
    mode = _parse_device_flag()
    if mode == "cpu":
        print("Device: CPU (default — pass --gpu/--cuda to use CUDA)")
        return {"CUDA_VISIBLE_DEVICES": ""}, None

    # --gpu/--cuda: leave CUDA_VISIBLE_DEVICES alone so a value set in .env
    # (already loaded into os.environ above) takes effect.
    if not _cuda_available():
        print("ERROR: --gpu/--cuda requested but no CUDA GPU is available.")
        print("Run `python run.py health --gpu` for hardware details.")
        return {}, 1
    print("Device: GPU (CUDA)")
    return {}, None


def _header(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n┌{bar}┐")
    print(f"│  {title}  │")
    print(f"└{bar}┘")
    sys.stdout.flush()  # ensure this prints before any subprocess output interleaves


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_app() -> int:
    env, early_exit = _resolve_device()
    if early_exit is not None:
        return early_exit
    if "--debug" in set(sys.argv[2:]):
        env["ALIENVOX_DEBUG"] = "1"
        print("Debug mode: ON — raw + enhanced text will be recorded in telemetry (.logs/*.jsonl)")
    _header("Starting AlienVox")
    # Run as a package module so relative imports work correctly.
    return _run(_venv_python(), "-m", "src.main", cwd=ROOT, env=env)


def cmd_health() -> int:
    env, early_exit = _resolve_device()
    if early_exit is not None:
        return early_exit
    _header("Health — imports, version pins, model weights")
    return _run(_venv_python(), "-m", "src.health", cwd=ROOT, env=env)


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
    env, early_exit = _resolve_device()
    if early_exit is not None:
        return early_exit
    _header("Perf — instrumentation benchmarks")

    # ── Unit benchmarks via pytest (config/registry/telemetry) ─────────────
    rc = _run(
        _venv_python(), "-m", "pytest",
        str(TESTS / "test_perf.py"),
        "-v", "--no-header", "--tb=short",
        "--no-cov",
        env=env,
    )

    # ── Real-speech benchmark (standalone — SAPI COM requires STA threading) ─
    _header("Perf — welcome phrase benchmark")
    rc_perf = _run(
        _venv_python(), "-m", "tests.test_perf", "_benchmark",
        env=env,
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
