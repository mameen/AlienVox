"""Four-layer YAML config resolver.

Layer 1: built-in defaults (this file)
Layer 2: stack.yaml  (.models/<stack>/stack.yaml)
Layer 3: model.yaml  (.models/<stack>/<model>/model.yaml)
Layer 4: user.yaml   (%LOCALAPPDATA%/com.alientech.alienvox/user.yaml)
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml


_DEFAULTS: dict = {
    "engine": "sapi5",
    "model": "",
    "voice": "",
    "rate": 0,
    "pitch": 0,
    "volume": 100,
    "ttl_seconds": 30,
    "hotkey": "<ctrl>+<esc>",
}


def _app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "com.alientech.alienvox"


def _models_root() -> Path:
    # Priority 1: user app data; Priority 3: dev override
    dev = Path(__file__).resolve().parents[2] / ".models"
    prod = _app_data_dir() / ".models"
    return prod if prod.exists() else dev


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_effective_config(stack: str = "", model: str = "") -> dict:
    cfg = dict(_DEFAULTS)
    models_root = _models_root()

    if stack:
        cfg.update(_load_yaml(models_root / stack / "stack.yaml"))
    if stack and model:
        cfg.update(_load_yaml(models_root / stack / model / "model.yaml"))

    cfg.update(_load_yaml(_app_data_dir() / "user.yaml"))
    return cfg


def save_user_override(patch: dict) -> None:
    user_file = _app_data_dir() / "user.yaml"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_yaml(user_file)
    existing.update(patch)
    with user_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f)
