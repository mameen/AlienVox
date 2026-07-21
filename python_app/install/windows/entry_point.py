"""Frozen-build entry point.

PyInstaller freezes whatever script Analysis() points at as a top-level
__main__ module with no parent package, so src/main.py's relative imports
(`from . import logger`, etc.) fail at runtime even though they work fine
under `python -m src.main` in dev. This wrapper imports src.main as a
proper package member first, then calls its main() — see alienvox.spec.
"""
import sys

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
