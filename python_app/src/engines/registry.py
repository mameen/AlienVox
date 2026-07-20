"""Stack registry — reads bundled stacks.yaml, checks weights on disk.

A stack/model is *available* when:
  - sapi5:  running on Windows (no weights needed)
  - ml/*:   weights_subpath exists under models_root

No filesystem scanning. The catalog is declared in stacks.yaml.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_stacks_catalog, models_root


def _speech_platform_installed() -> bool:
    """Return True if Microsoft Speech Platform v11 voices are present."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Speech Server\v11.0\Voices\Tokens",
        )
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


@dataclass
class ModelInfo:
    id: str
    name: str
    available: bool
    voices: list[dict[str, str]] = field(default_factory=list)


@dataclass
class StackInfo:
    id: str
    name: str
    available: bool
    platform_reason: str = ""
    models: list[ModelInfo] = field(default_factory=list)


def available_stacks(
    stacks_file: Path | None = None,
    models_root_override: Path | None = None,
) -> list[StackInfo]:
    """Return all stacks from stacks.yaml, each marked available/unavailable."""
    mr = models_root(models_root_override)
    catalog = load_stacks_catalog(stacks_file)
    result: list[StackInfo] = []

    for s in catalog:
        sid = s.get("id", "")
        platform = s.get("platform", "any")
        platform_ok = platform == "any" or platform == sys.platform

        if sid == "sapi5":
            # SAPI5 is always present on Windows, no weights to check
            result.append(StackInfo(
                id=sid,
                name=s.get("name", sid),
                available=sys.platform == "win32",
                platform_reason="" if sys.platform == "win32" else "Windows only",
                models=[],
            ))
            continue

        if sid == "speech_platform":
            # Microsoft Speech Platform (Speech Server v11) — present only when
            # the runtime + language packs are installed. Detect via registry.
            available = sys.platform == "win32" and _speech_platform_installed()
            result.append(StackInfo(
                id=sid,
                name=s.get("name", sid),
                available=available,
                platform_reason="" if sys.platform == "win32" else "Windows only",
                models=[],
            ))
            continue

        # ML / other stacks: check each model's weights
        model_infos: list[ModelInfo] = []
        for m in s.get("models", []):
            mid = m.get("id", "")
            weights = m.get("weights_subpath", "")
            weights_ok = bool(weights) and (mr / weights).exists()
            model_infos.append(ModelInfo(
                id=mid,
                name=m.get("name", mid),
                available=platform_ok and weights_ok,
                voices=m.get("voices", []),
            ))

        stack_available = platform_ok and any(m.available for m in model_infos)
        result.append(StackInfo(
            id=sid,
            name=s.get("name", sid),
            available=stack_available,
            platform_reason="" if platform_ok else f"{platform} only",
            models=model_infos,
        ))

    return result


def get_stack(
    stack_id: str,
    stacks_file: Path | None = None,
    models_root_override: Path | None = None,
) -> StackInfo | None:
    for s in available_stacks(stacks_file, models_root_override):
        if s.id == stack_id:
            return s
    return None
