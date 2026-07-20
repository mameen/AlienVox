"""Application version — loaded from version.yaml (single source of truth)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _version_path() -> Path:
    """Locate version.yaml: next to this module's parent (src/)."""
    return Path(__file__).resolve().parents[1] / "version.yaml"


def _load_version(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        path = _version_path()
    if not path.exists():
        return {"version": "0.0.0", "major": 0, "minor": 0, "build": 0}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


_VER_CACHE: dict[str, Any] | None = None


def _get_version() -> dict[str, Any]:
    global _VER_CACHE
    if _VER_CACHE is None:
        _VER_CACHE = _load_version()
    return _VER_CACHE


def version() -> str:
    """Return the full version string (e.g. '0.2.20260719143022')."""
    return str(_get_version().get("version", "0.0.0"))


def major() -> int:
    return int(_get_version().get("major", 0))


def minor() -> int:
    return int(_get_version().get("minor", 0))


def build() -> str:
    return str(_get_version().get("build", "0"))
