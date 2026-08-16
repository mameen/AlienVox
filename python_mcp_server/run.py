#!/usr/bin/env python3
"""AlienVox MCP server — task runner.

Usage:
    python run.py server    -- run the MCP server itself (stdio transport)
    python run.py inspect   -- launch the official MCP Inspector against this server
    python run.py test      -- run the real unit + smoke test suite (pytest)

All three commands run against THIS repo's own venv (../.venv — the one
with torch/kokoro/mcp already installed), not a fresh/isolated environment.

Why `inspect` doesn't just shell out to `mcp dev server.py`: that command
(mcp.cli.cli.dev) builds a `uv run --with mcp mcp run <file>` command under
the hood — an ISOLATED, ephemeral uv environment containing only the `mcp`
package itself, not this server's real dependencies (torch, kokoro,
soundfile, sounddevice). Running the Inspector that way would fail to
import alienvox_tts entirely. The MCP Inspector itself is generic
(`npx @modelcontextprotocol/inspector <command> <args...>` — it just
launches whatever command you give it as the server subprocess), so
`inspect` below invokes it directly against THIS repo's venv python,
skipping the `uv`-assuming wrapper — verified for real, not assumed (see
docs/20260816_agentic_requiremetns_and_plan.md for the sibling finding
about this SDK's `mcp dev` behavior).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SERVER_PY = ROOT / "server.py"
TESTS_DIR = ROOT / "tests"


def _venv_python() -> str:
    """Return this repo's own venv python, falling back to the current
    interpreter if that venv doesn't exist (e.g. a fresh checkout that
    hasn't been set up yet) — with a clear warning either way, since
    running against the wrong interpreter is a common source of confusing
    "ModuleNotFoundError" failures."""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    print(
        f"WARNING: {VENV_PYTHON} not found — falling back to {sys.executable}. "
        "torch/kokoro/mcp may not be installed there; see ../README.md for venv setup.",
        file=sys.stderr,
    )
    return sys.executable


def cmd_server() -> int:
    """Run the MCP server itself — stdio transport, waits for a real MCP
    client to connect. Appears to hang with no client attached; that's
    correct behavior, not a bug (see server.py's own module docstring)."""
    return subprocess.run([_venv_python(), str(SERVER_PY)], cwd=str(ROOT)).returncode


def cmd_inspect() -> int:
    """Launch the official MCP Inspector (Node-based, via npx) against
    this server, using THIS repo's venv python — not `mcp dev`'s isolated
    uv environment (see module docstring for why that would break)."""
    npx = shutil.which("npx")
    if npx is None:
        print(
            "ERROR: npx not found on PATH. The MCP Inspector is a Node.js tool "
            "(@modelcontextprotocol/inspector) — install Node.js from "
            "https://nodejs.org/ and ensure npx is on PATH, then retry.",
            file=sys.stderr,
        )
        return 1
    cmd = [npx, "@modelcontextprotocol/inspector", _venv_python(), str(SERVER_PY)]
    print(f"Launching MCP Inspector: {' '.join(cmd)}", file=sys.stderr)
    # shell=True on Windows: npx is npx.cmd, which cmd.exe needs shell=True
    # to resolve directly (same workaround the mcp package's own cli.py uses).
    return subprocess.run(cmd, cwd=str(ROOT), shell=(sys.platform == "win32")).returncode


def cmd_test() -> int:
    """Run the real test suite (tests/test_tools.py, tests/test_server.py)
    — real synthesis, real MCP SDK registration checks, no mocking (see
    ../python_app's own .agents/SKILLS/testing/SKILL.md for why this repo
    takes that stance everywhere)."""
    return subprocess.run(
        [_venv_python(), "-m", "pytest", str(TESTS_DIR), "-v"], cwd=str(ROOT)
    ).returncode


COMMANDS = {
    "server": cmd_server,
    "inspect": cmd_inspect,
    "test": cmd_test,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(COMMANDS)}")
        return 1
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
