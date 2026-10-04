#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Package the alien_stt skill into a single zip for deployment.

    python build.py

Zips this whole folder into ``.build/alien_stt.zip``. The skill is
self-sufficient (vendored ``alienstt/``, its own ``scripts/requirements.txt``), so
the zip can be unpacked on another machine and run after installing the
requirements and ffmpeg.

Excluded: virtual environments, bytecode, caches and ``.build`` itself. Everything
else ships, including ``assets/sample_speech.wav`` and ``tests/``.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
BUILD_DIR = SKILL_ROOT / ".build"
OUTPUT_ZIP = BUILD_DIR / "alien_stt.zip"

_EXCLUDE_DIR_NAMES = {".venv", "__pycache__", ".build", ".pytest_cache"}


def _should_include(path: Path) -> bool:
    """True unless any folder in the path (relative to the skill root) is excluded."""
    return not any(part in _EXCLUDE_DIR_NAMES for part in path.relative_to(SKILL_ROOT).parts)


def main() -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()
    files = [p for p in sorted(SKILL_ROOT.rglob("*"))
             if p.is_file() and p.suffix != ".pyc" and _should_include(p)]
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, Path("alien_stt") / f.relative_to(SKILL_ROOT))
    print(f"Built {OUTPUT_ZIP} ({len(files)} files, {OUTPUT_ZIP.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
