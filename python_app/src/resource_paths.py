"""Helpers for locating bundled UI resources in dev and frozen builds."""
from __future__ import annotations

import sys
from pathlib import Path


def resources_root() -> Path:
    """Return the directory containing bundled app resources.

    Dev mode keeps resources under ``python_app/src/resources``.
    Frozen installs place them under ``<app>/__internal__/resources``.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        internal = exe_dir / "_internal"
        if (internal / "resources").exists():
            return internal / "resources"
        if (exe_dir / "resources").exists():
            return exe_dir / "resources"
    return Path(__file__).resolve().parent / "resources"


def resource_path(*parts: str) -> Path:
    return resources_root().joinpath(*parts)
