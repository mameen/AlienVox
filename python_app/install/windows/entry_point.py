"""Frozen-build entry point.

PyInstaller freezes whatever script Analysis() points at as a top-level
__main__ module with no parent package, so src/main.py's relative imports
(`from . import logger`, etc.) fail at runtime even though they work fine
under `python -m src.main` in dev. This wrapper imports src.main as a
proper package member first, then calls its main() — see alienvox.spec.
"""
import sys

if getattr(sys, "frozen", False):
    from pathlib import Path
    import os

    frozen_root = Path(sys.executable).resolve().parent
    internal_root = frozen_root / "_internal"
    pyside_root = internal_root / "PySide6"
    plugin_root = pyside_root / "plugins"
    candidate_dirs = [
        pyside_root,
        internal_root / "shiboken6",
        internal_root,
    ]
    _dll_directory_handles = []
    for dll_dir in candidate_dirs:
        if dll_dir.exists():
            try:
                _dll_directory_handles.append(os.add_dll_directory(str(dll_dir)))
            except (AttributeError, FileNotFoundError, OSError):
                pass
    if plugin_root.exists():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(plugin_root / "platforms"))
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    existing_path = os.environ.get("PATH", "")
    dll_path_prefix = os.pathsep.join(str(p) for p in candidate_dirs if p.exists())
    if dll_path_prefix:
        os.environ["PATH"] = dll_path_prefix + (os.pathsep + existing_path if existing_path else "")

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
