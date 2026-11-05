"""Model/voice install & uninstall — the business logic behind Manage Voices'
per-model and per-voice Install/Uninstall buttons.

Pure functions, no Qt — ManageVoicesDialog wraps download_model() in its own
background QThread for progress-signal safety (Qt-specific, legitimately a
View concern), but the actual "what to fetch and where" logic lives here so
it's callable/testable without a running Qt app, same split as
text_enhancer.py already established for AppController.

Known duplication (not resolved here — out of scope for this change):
setup.py's `_download_kokoro`/`_download_piper`/`_download_auto` implement
the same downloads for `python setup.py download`. Both call the same
underlying HF repos; a future pass could have one call the other instead of
maintaining two copies, but setup.py runs before the venv is fully set up
(bootstrap constraints), so unifying them needs more care than this change
warrants.
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Callable

from .. import logger as _logger_mod

_log = _logger_mod.get_logger("model_installer")

ProgressCb = Callable[[int, int, str], None]  # (done, total, description)

_HF_REPOS = {
    "kokoro": "hexgrad/Kokoro-82M",
    "chatterbox": "ResembleAI/chatterbox",
    "dia": "nari-labs/Dia-1.6B-0626",
    "f5tts": "SWivid/F5-TTS",
    "outetts": "OuteAI/OuteTTS-0.3-500M",
    "vibevoice_realtime": "microsoft/VibeVoice-Realtime-0.5B",
    "supertonic3": "supertone-oss-archive/supertonic-3",
}
_MOSS_REPOS = {
    "MOSS-TTS-Nano-100M-ONNX": "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX",
    "MOSS-Audio-Tokenizer-Nano-ONNX": "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX",
}
_HF_REVISIONS = {
    # Upstream archived this model repo; pin the verified snapshot so installs
    # reproduce the file layout expected by the Supertonic 3 adapter.
    "supertonic3": "aafc6e32416a594460b32413efc49d7fe4ce6d46",
}
_PIPER_HF_REPO = "rhasspy/piper-voices"
_VIBEVOICE_VOICE_PT_BASE_URL = (
    "https://raw.githubusercontent.com/microsoft/VibeVoice/main/"
    "demo/voices/streaming_model/"
)
_VIBEVOICE_VOICE_FILES = {
    "carter": "en-Carter_man.pt", "davis": "en-Davis_man.pt",
    "frank": "en-Frank_man.pt", "mike": "en-Mike_man.pt",
    "emma": "en-Emma_woman.pt", "grace": "en-Grace_woman.pt",
}


def _piper_subpath(voice_id: str) -> str:
    """rhasspy/piper-voices path layout: {lang}/{lang_full}/{name}/{quality}/{file}
    e.g. en/en_US/lessac/medium/en_US-lessac-medium.onnx"""
    parts = voice_id.split("-")
    if len(parts) < 3:
        return voice_id
    lang_full = parts[0]
    name = "-".join(parts[1:-1])
    quality = parts[-1]
    lang_short = lang_full.split("_")[0]
    return f"{lang_short}/{lang_full}/{name}/{quality}"


def download_model(
    stack_id: str,
    model_id: str,
    models_root: Path,
    on_progress: ProgressCb,
    voice_id: str | None = None,
) -> None:
    """Download a model's weights (or, for Piper, one voice's files).

    voice_id is required for piper (per-voice download), ignored for every
    other model (whole-model download covers all its voices at once).
    """
    if model_id == "piper":
        if not voice_id:
            raise ValueError("piper downloads require voice_id")
        _download_piper_voice(voice_id, models_root, on_progress)
        return

    if model_id == "pockettts":
        _download_pockettts(models_root, on_progress)
        return

    if model_id == "moss_tts_nano":
        from huggingface_hub import snapshot_download

        dest = models_root / "ml" / model_id
        for folder, repo in _MOSS_REPOS.items():
            on_progress(0, 2, f"Downloading {folder}…")
            snapshot_download(
                repo_id=repo,
                local_dir=str(dest / folder),
                tqdm_class=None,
            )
        return

    if model_id not in _HF_REPOS:
        raise ValueError(f"no download strategy for model '{model_id}'")

    dest = models_root / "ml" / model_id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "Missing downloader dependency 'huggingface_hub'. "
            "Please reinstall the app or run the full installer again."
        ) from exc

    def _progress_cb(transferred: int, total: int) -> None:
        on_progress(transferred, total, f"{model_id}  {transferred // 1_048_576} / {max(total, 1) // 1_048_576} MB")

    _log.info("downloading %s to %s", model_id, dest)
    download_args = {"repo_id": _HF_REPOS[model_id], "local_dir": str(dest), "tqdm_class": None}
    if model_id in _HF_REVISIONS:
        download_args["revision"] = _HF_REVISIONS[model_id]
    snapshot_download(**download_args)
    _log.info("%s download complete -> %s", model_id, dest)

    if model_id == "f5tts":
        from ..engines.f5tts_engine import provision_reference_voices
        provision_reference_voices(dest / "voices")
    elif model_id == "vibevoice_realtime":
        _download_vibevoice_voices(dest, on_progress)


def _download_vibevoice_voices(dest: Path, on_progress: ProgressCb) -> None:
    voices_dir = dest / "voices"
    voices_dir.mkdir(exist_ok=True)
    for i, (voice_id, filename) in enumerate(_VIBEVOICE_VOICE_FILES.items()):
        on_progress(i, len(_VIBEVOICE_VOICE_FILES), f"Downloading preset voice {filename}…")
        dest_pt = voices_dir / filename
        if dest_pt.exists():
            continue
        try:
            urllib.request.urlretrieve(_VIBEVOICE_VOICE_PT_BASE_URL + filename, str(dest_pt))
        except Exception as exc:
            _log.error("failed to download %s: %s", filename, exc)
            raise
    _log.info("VibeVoice preset voices ready -> %s", voices_dir)


def _download_pockettts(models_root: Path, on_progress: ProgressCb) -> None:
    """Install the public no-voice-cloning checkpoint and preset embeddings locally."""
    try:
        import yaml
        from huggingface_hub import hf_hub_download
        from pocket_tts.utils.config import CONFIGS_DIR
    except ImportError as exc:
        raise RuntimeError(
            "Pocket TTS is an optional dependency; install it with `pip install --no-deps pocket-tts==4.0.1` "
            "after confirming it is compatible with this environment."
        ) from exc

    dest = models_root / "ml" / "pockettts"
    voices_dir = dest / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    repo = "kyutai/pocket-tts-without-voice-cloning"
    revision = "a7056f505a4a8ca72d8b5fb1440071d6f1a35739"
    files = [
        "languages/english/model.safetensors",
        "languages/english/tokenizer.json",
        "languages/english/embeddings/alba.safetensors",
        "languages/english/embeddings/marius.safetensors",
    ]
    downloaded: dict[str, Path] = {}
    for index, filename in enumerate(files, 1):
        on_progress(index - 1, len(files), f"Pocket TTS {filename.rsplit('/', 1)[-1]}")
        downloaded[filename] = Path(hf_hub_download(
            repo_id=repo,
            filename=filename,
            revision=revision,
            local_dir=str(dest),
        ))

    import yaml
    config = yaml.safe_load((Path(CONFIGS_DIR) / "english.yaml").read_text(encoding="utf-8"))
    config["weights_path"] = str(downloaded[files[0]])
    config["weights_path_without_voice_cloning"] = None
    config["flow_lm"]["lookup_table"]["tokenizer_path"] = str(downloaded[files[1]])
    (dest / "english.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    for voice, filename in (("alba", files[2]), ("marius", files[3])):
        target = voices_dir / f"{voice}.safetensors"
        if downloaded[filename] != target:
            shutil.copy2(downloaded[filename], target)
    on_progress(len(files), len(files), "Pocket TTS installed")


def _download_piper_voice(voice_id: str, models_root: Path, on_progress: ProgressCb) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "Missing downloader dependency 'huggingface_hub'. "
            "Please reinstall the app or run the full installer again."
        ) from exc
    dest = models_root / "ml" / "piper"
    dest.mkdir(parents=True, exist_ok=True)
    subpath = _piper_subpath(voice_id)

    files = [f"{voice_id}.onnx", f"{voice_id}.onnx.json"]
    for i, fname in enumerate(files):
        on_progress(i, len(files), f"Downloading {fname}…")
        _log.info("downloading piper voice file: %s", fname)
        try:
            hf_hub_download(
                repo_id=_PIPER_HF_REPO,
                filename=f"{subpath}/{fname}",
                local_dir=str(dest),
                local_dir_use_symlinks=False,
            )
        except Exception as exc:
            _log.error("failed to download %s: %s", fname, exc)
            raise


def piper_voice_installed(voice_id: str, models_root: Path) -> bool:
    dest = models_root / "ml" / "piper"
    return bool(dest.exists() and list(dest.rglob(f"{voice_id}.onnx")))


def uninstall_model(stack_id: str, model_id: str, models_root: Path) -> None:
    """Delete a model's entire weights directory — every voice sharing that
    model's weights goes with it (Kokoro/Chatterbox/Dia/F5-TTS/OuteTTS/
    VibeVoice all share one weights blob across their voices). Not for
    Piper — see uninstall_piper_voice() for that per-voice case."""
    dest = models_root / "ml" / model_id
    if dest.exists():
        _log.info("removing %s", dest)
        shutil.rmtree(dest, ignore_errors=True)


def uninstall_piper_voice(voice_id: str, models_root: Path) -> None:
    dest = models_root / "ml" / "piper"
    if not dest.exists():
        return
    for f in dest.rglob(f"{voice_id}.onnx*"):
        if f.is_file():
            _log.info("removing %s", f)
            f.unlink()
