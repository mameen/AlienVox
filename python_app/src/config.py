"""Config resolver — reads bundled stacks.yaml + user.yaml overrides.

Resolution order (later wins):
  Layer 1: built-in defaults (this module)
  Layer 2+3: stacks.yaml  — bundled with the app; declares all stacks, models, controls, voices
  Layer 4: user.yaml      — user overrides, saved instantly on every change

Both stacks.yaml and user.yaml live next to the app, not hidden in
%LOCALAPPDATA% — easy to find, inspect, back up, or delete to reset:
  - Dev mode:    next to setup.py  (<repo>/python_app/{stacks,user}.yaml)
  - Production:  next to the executable

This module is pure (no side-effects, no global state) except for
user_yaml_path()'s one-time migration of a pre-existing AppData user.yaml
(from before this file moved next to the app) on first read.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

# ── Built-in defaults (Layer 1) ──────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "engine": "sapi5",
    "model": "",
    "voice": "",
    "rate": 0,
    "pitch": 0,
    "volume": 100,
    "ttl_seconds": 30,
    "hotkey": "<ctrl>+<esc>",
}

# ── Path helpers ──────────────────────────────────────────────────────────────

def app_data_dir() -> Path:
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        import os
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "com.alientech.alienvox"


def stacks_yaml_path(override: Path | None = None) -> Path:
    """Locate stacks.yaml: explicit override → next to exe → dev fallback."""
    if override is not None:
        return override
    # When frozen by PyInstaller, sys.executable is the .exe
    exe_sibling = Path(sys.executable).parent / "stacks.yaml"
    if exe_sibling.exists():
        return exe_sibling
    # Dev: <repo>/python_app/stacks.yaml
    return Path(__file__).resolve().parents[1] / "stacks.yaml"


def user_yaml_path(override: Path | None = None) -> Path:
    """Locate user.yaml: explicit override → next to exe → dev fallback.

    Same resolution pattern as stacks_yaml_path() — lives next to the app,
    not in %LOCALAPPDATA%, so settings are easy to find/back up/reset.

    One-time migration: if this path doesn't exist yet but an older
    AppData-based user.yaml does (from before this moved), copy it over so
    existing settings aren't silently lost.
    """
    if override is not None:
        return override
    exe_sibling = Path(sys.executable).parent / "stacks.yaml"
    target = (exe_sibling.parent if exe_sibling.exists()
              else Path(__file__).resolve().parents[1]) / "user.yaml"

    if not target.exists():
        legacy = app_data_dir() / "user.yaml"
        if legacy.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(legacy.read_bytes())
            except OSError:
                pass  # best-effort migration — fall through to defaults if it fails

    return target


def models_root(override: Path | None = None) -> Path:
    """Return the directory where model weights live.

    Search order:
      1. explicit override (tests)
      2. app-data dir  (%LOCALAPPDATA%/com.alientech.alienvox/.models)
      3. dev override  (<repo>/python_app/.models)
    """
    if override is not None:
        return override
    prod = app_data_dir() / ".models"
    if prod.exists():
        return prod
    return Path(__file__).resolve().parents[1] / ".models"


# ── YAML helpers ──────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _merge(*layers: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in layers:
        result.update(layer)
    return result


# ── Stacks catalog ────────────────────────────────────────────────────────────

def load_stacks_catalog(stacks_file: Path | None = None) -> list[dict[str, Any]]:
    """Return the raw list of stack dicts from stacks.yaml."""
    path = stacks_yaml_path(stacks_file)
    data = _load_yaml(path)
    return data.get("stacks", [])


def get_stack_def(stack_id: str, stacks_file: Path | None = None) -> dict[str, Any]:
    for s in load_stacks_catalog(stacks_file):
        if s.get("id") == stack_id:
            return s
    return {}


def get_model_def(stack_id: str, model_id: str, stacks_file: Path | None = None) -> dict[str, Any]:
    stack = get_stack_def(stack_id, stacks_file)
    for m in stack.get("models", []):
        if m.get("id") == model_id:
            return m
    return {}


def list_stacks(stacks_file: Path | None = None) -> list[str]:
    return [s["id"] for s in load_stacks_catalog(stacks_file) if "id" in s]


def list_models(stack_id: str, stacks_file: Path | None = None) -> list[str]:
    stack = get_stack_def(stack_id, stacks_file)
    return [m["id"] for m in stack.get("models", []) if "id" in m]


def get_voices(
    stack_id: str,
    model_id: str = "",
    stacks_file: Path | None = None,
) -> list[dict[str, str]]:
    if model_id:
        defn = get_model_def(stack_id, model_id, stacks_file)
    else:
        defn = get_stack_def(stack_id, stacks_file)
    return defn.get("voices", [])


def get_controls(
    stack_id: str,
    model_id: str = "",
    stacks_file: Path | None = None,
    stacks_yaml: Path | None = None,  # alias accepted from tests
) -> dict[str, Any]:
    if stacks_yaml is not None and stacks_file is None:
        stacks_file = stacks_yaml
    if model_id:
        defn = get_model_def(stack_id, model_id, stacks_file)
    else:
        defn = get_stack_def(stack_id, stacks_file)
    return defn.get("controls", {})


# ── Config resolution ─────────────────────────────────────────────────────────

def load_effective_config(
    stack_id: str = "",
    model_id: str = "",
    stacks_file: Path | None = None,
    user_file: Path | None = None,
) -> dict[str, Any]:
    """Return the full four-layer merged config for a given stack/model."""
    uf = user_file if user_file is not None else user_yaml_path()

    stack_layer: dict[str, Any] = {}
    model_layer: dict[str, Any] = {}

    if stack_id:
        s = get_stack_def(stack_id, stacks_file)
        stack_layer = {k: v for k, v in s.items() if k not in ("id", "models", "controls", "voices", "weights_subpath")}
    if stack_id and model_id:
        m = get_model_def(stack_id, model_id, stacks_file)
        model_layer = {k: v for k, v in m.items() if k not in ("id", "controls", "voices", "weights_subpath")}

    user_layer = _load_yaml(uf)
    return _merge(DEFAULTS, stack_layer, model_layer, user_layer)


def save_user_override(patch: dict[str, Any], user_file: Path | None = None) -> None:
    uf = user_file if user_file is not None else user_yaml_path()
    uf.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_yaml(uf)
    existing.update(patch)
    with uf.open("w", encoding="utf-8") as f:
        yaml.safe_dump(existing, f, allow_unicode=True)
