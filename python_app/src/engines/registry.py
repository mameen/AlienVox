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


def _detect_speech_platform_via_registry() -> bool:
    """One-shot registry probe — only called when the cache file is absent."""
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


def _platform_cache_path() -> Path:
    """platform.yaml lives next to stacks.yaml so it travels with the app."""
    from ..config import stacks_yaml_path
    return stacks_yaml_path().parent / "platform.yaml"


def _platform_example_path() -> Path:
    from ..config import stacks_yaml_path
    return stacks_yaml_path().parent / "platform.yaml.example"


def _speech_platform_installed() -> bool:
    """Return True if Microsoft Speech Platform v11 voices are present.

    Result is cached in platform.yaml next to stacks.yaml.  Delete that file
    to force re-detection (e.g. after installing the Speech Platform runtime).
    """
    if sys.platform != "win32":
        return False

    import yaml

    cache = _platform_cache_path()
    if cache.exists():
        try:
            with cache.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return bool(data.get("speech_platform_installed", False))
        except Exception:
            pass  # corrupt cache → fall through to re-detect

    result = _detect_speech_platform_via_registry()
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        # Seed from the committed example so the file format is self-documenting.
        example = _platform_example_path()
        if example.exists():
            import re
            text = example.read_text(encoding="utf-8")
            text = re.sub(
                r"^(speech_platform_installed:\s*).*$",
                rf"\g<1>{str(result).lower()}",
                text,
                flags=re.MULTILINE,
            )
            cache.write_text(text, encoding="utf-8")
        else:
            with cache.open("w", encoding="utf-8") as f:
                yaml.dump({"speech_platform_installed": result}, f)
    except Exception:
        pass  # cache write failure is non-fatal
    return result


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

        # ML / other stacks: check each model's weights.
        # Models with auto_download=true are always available (weights fetched on demand).
        model_infos: list[ModelInfo] = []
        for m in s.get("models", []):
            mid = m.get("id", "")
            weights = m.get("weights_subpath", "")
            auto_dl = m.get("auto_download", False)
            weights_ok = auto_dl or (bool(weights) and (mr / weights).exists())
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
