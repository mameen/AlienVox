"""Build-time installer asset helper.

Downloads required third-party installer assets on demand so the repo
does not need to store large redistributable binaries under source
control.
"""
from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve


ROOT = Path(__file__).resolve().parent
VC_REDIST_URL = "https://aka.ms/vc14/vc_redist.x64.exe"
VC_REDIST_PATH = ROOT / "windows" / "exe" / "redist" / "VC_redist.x64.exe"


def ensure_vc_redist() -> Path:
    VC_REDIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not VC_REDIST_PATH.exists() or VC_REDIST_PATH.stat().st_size < 1_000_000:
        tmp_path = VC_REDIST_PATH.with_suffix(".download")
        if tmp_path.exists():
            tmp_path.unlink()
        urlretrieve(VC_REDIST_URL, tmp_path)
        tmp_path.replace(VC_REDIST_PATH)
    return VC_REDIST_PATH


def main() -> int:
    path = ensure_vc_redist()
    print(f"VC++ redist ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
