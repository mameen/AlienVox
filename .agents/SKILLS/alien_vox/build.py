#!/usr/bin/env python3
"""Package the alien_vox skill for deployment.

Zips this entire skill folder into .build/alien_vox.zip — a self-contained
artifact (the skill is self-sufficient: vendored alienvox_tts/, its own
scripts/requirements.txt) that can be copied to another machine/repo,
unzipped, and run with no sibling ../../../python_lib dependency.

Excludes dev-only content that shouldn't ship: .venv/, __pycache__/, .build/
itself, and any .pyc files — everything else in this folder is included.

Usage:
    python build.py
"""
from __future__ import annotations

import zipfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent
BUILD_DIR = SKILL_ROOT / ".build"
OUTPUT_ZIP = BUILD_DIR / "alien_vox.zip"

_EXCLUDE_DIR_NAMES = {".venv", "__pycache__", ".build", ".pytest_cache"}


def _should_include(path: Path) -> bool:
    return not any(part in _EXCLUDE_DIR_NAMES for part in path.relative_to(SKILL_ROOT).parts)


def main() -> int:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    files = [
        p for p in SKILL_ROOT.rglob("*")
        if p.is_file() and p.suffix != ".pyc" and _should_include(p)
    ]

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arcname = Path("alien_vox") / f.relative_to(SKILL_ROOT)
            zf.write(f, arcname)

    size_kb = OUTPUT_ZIP.stat().st_size / 1024
    print(f"Built {OUTPUT_ZIP} ({len(files)} files, {size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
