"""AlienVox python_app bootstrap — creates venv and installs requirements."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"


def venv_python() -> str:
    if sys.platform.startswith("win"):
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT).returncode


def main() -> int:
    print("AlienVox python_app bootstrap")
    print(f"Python: {sys.version.splitlines()[0]}")

    if not VENV_DIR.exists():
        print(f"Creating venv at {VENV_DIR}...")
        if run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            print("ERROR: venv creation failed.")
            return 1
    else:
        print(f"Using existing venv at {VENV_DIR}")

    python = venv_python()
    print("\nUpgrading pip...")
    run([python, "-m", "pip", "install", "--upgrade", "pip"])

    req = ROOT / "requirements.txt"
    print(f"\nInstalling {req.name}...")
    print("(torch alone is ~2 GB on first install — this will take a while)")
    rc = run([python, "-m", "pip", "install", "-r", str(req)])
    if rc != 0:
        print("WARNING: Some packages failed. Check the output above.")

    print("\nInstalling Dia from source (no stable PyPI release)...")
    run([python, "-m", "pip", "install", "git+https://github.com/nari-labs/dia.git"])

    print("\nBootstrap complete.")
    print(f"Activate venv:  {VENV_DIR}\\Scripts\\activate")
    print("Run app:        python -m src.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
