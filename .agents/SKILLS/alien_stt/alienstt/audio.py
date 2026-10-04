#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audio input/output for alienstt: find files, probe them, decode, convert, split.

This is the layer that turns "whatever file the user has" into "the 16 kHz
mono float32 array every engine wants", and the layer behind the standalone
conversion and splitting tools. It knows about files and ffmpeg. It does not
know about models, transcripts or output formats.

Why ffmpeg and not a Python audio library
-----------------------------------------
Voice notes arrive as Ogg/Opus, phone recordings as AMR or M4A, meetings as
MP4 or MKV with a video stream, podcasts as MP3. `soundfile` reads a handful of
those; ffmpeg reads essentially all of them and can extract the audio track of
a video in the same call. One dependency, one code path, every format.

Decoding goes through a pipe (`-f f32le pipe:1`) rather than a temporary WAV
file. It is faster, leaves nothing on disk to clean up, and cannot collide with
a parallel run that picked the same temp name.

Locating ffmpeg
---------------
Order: the ``FFMPEG`` / ``FFPROBE`` environment variable (a full path to the
executable), then ``PATH``. There is deliberately no hard-coded install
location: a path that exists on one machine is a bug on every other one.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import numpy as np

from .base import SAMPLE_RATE

#: Extensions treated as audio when a folder is scanned. ffmpeg can read far
#: more; this list only decides what a *folder scan* picks up. A file named
#: explicitly is always attempted, whatever its extension.
AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".wav", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma",
    ".amr", ".aiff", ".aif", ".ac3", ".mp2", ".mpa", ".caf", ".weba",
})

#: Containers that usually carry a video stream. The audio track is extracted.
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".3gp", ".flv", ".wmv", ".ts",
})

MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


class AudioError(RuntimeError):
    """ffmpeg/ffprobe ran and failed, or produced something unusable."""


class ToolNotFoundError(AudioError):
    """ffmpeg or ffprobe is not installed or not discoverable."""


def find_tool(name: str) -> str:
    """Return the path of `name` (``"ffmpeg"`` or ``"ffprobe"``).

    Checks the upper-cased environment variable first (``FFMPEG``, ``FFPROBE``),
    then ``PATH``. ffprobe additionally looks next to a configured ``FFMPEG``,
    because the two almost always ship in the same folder.

    Raises `ToolNotFoundError` with an install hint instead of exiting, so a
    library caller can handle it and a CLI can print it.
    """
    configured = os.environ.get(name.upper())
    if configured and pathlib.Path(configured).exists():
        return configured
    on_path = shutil.which(name)
    if on_path:
        return on_path
    if name == "ffprobe":
        ffmpeg = os.environ.get("FFMPEG")
        if ffmpeg:
            sibling = pathlib.Path(ffmpeg).with_name("ffprobe" + pathlib.Path(ffmpeg).suffix)
            if sibling.exists():
                return str(sibling)
    raise ToolNotFoundError(
        f"{name} not found. Install ffmpeg (https://ffmpeg.org/download.html), add it to PATH, "
        f"or set the {name.upper()} environment variable to the full path of {name}."
    )


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    """Run a command, capturing bytes; raise `AudioError` with ffmpeg's own message on failure."""
    proc = subprocess.run(list(cmd), capture_output=True)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip() or f"exit code {proc.returncode}"
        raise AudioError(f"{pathlib.Path(cmd[0]).name} failed: {message}")
    return proc


# --------------------------------------------------------------------------- finding files
def collect_inputs(
    inputs: Iterable[str | os.PathLike],
    extensions: Optional[Iterable[str]] = None,
    recursive: bool = False,
    dedupe: bool = True,
) -> tuple[list[pathlib.Path], list[str]]:
    """Expand files and folders into a flat, ordered list of media files.

    Parameters
    ----------
    inputs:
        Files and/or folders. A file is always included, whatever its
        extension. A folder contributes the files whose extension is in
        `extensions` (default `MEDIA_EXTENSIONS`).
    recursive:
        Descend into sub-folders. Off by default so pointing at a big folder
        does not silently queue thousands of files.
    dedupe:
        Keep only the first file for each ``(folder, stem)``. A voice-note
        folder often holds ``x.ogg`` *and* its converted ``x.mp3``; both would
        write the same ``x.*`` outputs, so doing the work twice is wasted and
        the second write would overwrite the first.

    Returns
    -------
    ``(files, notes)`` where `notes` is a list of human-readable skip messages
    (missing path, duplicate stem) for the caller to print or log.
    """
    exts = frozenset(e.lower() if e.startswith(".") else "." + e.lower() for e in (extensions or MEDIA_EXTENSIONS))
    files: list[pathlib.Path] = []
    notes: list[str] = []
    for item in inputs:
        p = pathlib.Path(item)
        if p.is_dir():
            walker = p.rglob("*") if recursive else p.iterdir()
            files += sorted(f for f in walker if f.is_file() and f.suffix.lower() in exts)
        elif p.is_file():
            files.append(p)
        else:
            notes.append(f"not found: {item}")
    if not dedupe:
        return files, notes
    seen: dict[tuple[pathlib.Path, str], pathlib.Path] = {}
    unique: list[pathlib.Path] = []
    for f in files:
        key = (f.parent, f.stem)
        if key in seen:
            notes.append(f"skipped {f.name}: same name as {seen[key].name}")
            continue
        seen[key] = f
        unique.append(f)
    return unique, notes


# --------------------------------------------------------------------------- probing
@dataclass
class AudioInfo:
    """What ffprobe reports about a media file's first audio stream."""

    path: str
    duration: float
    format_name: str
    audio_codec: Optional[str]
    sample_rate: Optional[int]
    channels: Optional[int]
    bit_rate: Optional[int]
    has_video: bool
    size_bytes: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def probe(path: str | os.PathLike) -> AudioInfo:
    """Inspect a media file without decoding it.

    Raises `AudioError` if the file has no audio stream; a file that decodes to
    nothing would otherwise "succeed" later with an empty transcript, which is
    a quiet way to lose a recording.
    """
    p = pathlib.Path(path)
    out = _run([find_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)])
    data = json.loads(out.stdout.decode("utf-8", "replace"))
    streams = data.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise AudioError(f"{p.name} has no audio stream")
    fmt = data.get("format", {})

    def _num(value, cast):
        try:
            return cast(value)
        except (TypeError, ValueError):
            return None

    duration = _num(fmt.get("duration"), float) or _num(audio.get("duration"), float) or 0.0
    return AudioInfo(
        path=str(p),
        duration=duration,
        format_name=str(fmt.get("format_name", "")),
        audio_codec=audio.get("codec_name"),
        sample_rate=_num(audio.get("sample_rate"), int),
        channels=_num(audio.get("channels"), int),
        bit_rate=_num(audio.get("bit_rate") or fmt.get("bit_rate"), int),
        has_video=any(s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") for s in streams),
        size_bytes=p.stat().st_size,
    )


# --------------------------------------------------------------------------- decoding
def decode(
    path: str | os.PathLike,
    sample_rate: int = SAMPLE_RATE,
    start: Optional[float] = None,
    duration: Optional[float] = None,
) -> np.ndarray:
    """Decode any media file to mono float32 samples at `sample_rate`.

    `start`/`duration` (seconds) decode just a slice; the seek happens before
    the input is opened so ffmpeg skips ahead instead of decoding and discarding.
    Stereo and surround are down-mixed to mono. Video tracks are ignored.

    Raises `AudioError` if ffmpeg fails or yields no samples.
    """
    cmd = [find_tool("ffmpeg"), "-nostdin", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    samples = np.frombuffer(_run(cmd).stdout, dtype=np.float32).copy()
    if samples.size == 0:
        raise AudioError(f"decoded no audio from {pathlib.Path(path).name}")
    return samples


# --------------------------------------------------------------------------- converting
#: Lossy containers get a sane default bitrate; lossless ones ignore bitrate.
_LOSSY_DEFAULT_BITRATE = {".mp3": "128k", ".m4a": "128k", ".aac": "128k", ".opus": "64k", ".wma": "128k"}

#: Vorbis refuses many fixed bitrates at low sample rates ("encoder setup failed"),
#: so for Ogg Vorbis the default is a quality level (0-10) instead of a bitrate.
_VORBIS_EXTENSIONS = {".ogg", ".oga"}


def convert(
    src: str | os.PathLike,
    dst: str | os.PathLike,
    *,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    bitrate: Optional[str] = None,
    start: Optional[float] = None,
    duration: Optional[float] = None,
    overwrite: bool = False,
) -> pathlib.Path:
    """Convert or slice a media file; the output format follows `dst`'s extension.

    Examples: Ogg/Opus voice note to MP3, a video to its audio track as WAV, a
    two-minute slice of a long recording to FLAC.

    Refuses to overwrite an existing file unless `overwrite=True`, so a typo in
    the destination cannot destroy a recording. Writes to a sibling temporary
    name first and renames on success, so an interrupted run leaves no
    half-written file under the final name.
    """
    s, d = pathlib.Path(src), pathlib.Path(dst)
    if not s.is_file():
        raise AudioError(f"source not found: {s}")
    if d.exists() and not overwrite:
        raise AudioError(f"destination exists (pass overwrite=True to replace): {d}")
    if s.resolve() == d.resolve():
        raise AudioError("source and destination are the same file")
    d.parent.mkdir(parents=True, exist_ok=True)
    bitrate = bitrate or _LOSSY_DEFAULT_BITRATE.get(d.suffix.lower())

    cmd = [find_tool("ffmpeg"), "-nostdin", "-loglevel", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(s), "-vn", "-map_metadata", "-1"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]
    if channels:
        cmd += ["-ac", str(channels)]
    if bitrate:
        cmd += ["-b:a", bitrate]
    elif d.suffix.lower() in _VORBIS_EXTENSIONS:
        cmd += ["-q:a", "4"]
    tmp = d.with_name(d.stem + ".partial" + d.suffix)
    cmd.append(str(tmp))
    try:
        _run(cmd)
        os.replace(tmp, d)
    finally:
        if tmp.exists():
            tmp.unlink()
    return d


# --------------------------------------------------------------------------- quiet gaps and chunking
def quiet_ranges(
    audio: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    threshold_db: float = -40.0,
    min_silence: float = 0.4,
    frame_ms: float = 30.0,
) -> list[tuple[float, float]]:
    """Find stretches of near-silence as ``(start, end)`` seconds.

    Pure numpy on already-decoded audio, so it needs no ffmpeg and works the
    same on a slice held in memory. A frame is "quiet" when its RMS level is
    below `threshold_db` dBFS (``0`` is full scale; speech usually sits around
    -30 to -15, room tone around -60 to -45). Adjacent quiet frames merge, and
    a run shorter than `min_silence` seconds is ignored.

    Tune `threshold_db` up (towards -30) for noisy recordings where "silence"
    is never very quiet, and down (towards -50) for clean ones with soft speech.
    """
    frame = max(1, int(sample_rate * frame_ms / 1000.0))
    n = audio.size // frame
    if n == 0:
        return []
    rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    quiet = 20.0 * np.log10(rms) < threshold_db
    ranges: list[tuple[float, float]] = []
    run_start: Optional[int] = None
    for i, q in enumerate(np.append(quiet, False)):          # trailing False closes a final run
        if q and run_start is None:
            run_start = i
        elif not q and run_start is not None:
            a, b = run_start * frame / sample_rate, i * frame / sample_rate
            if b - a >= min_silence:
                ranges.append((round(a, 3), round(b, 3)))
            run_start = None
    return ranges


def plan_chunks(
    duration: float,
    quiet: Sequence[tuple[float, float]],
    max_seconds: float,
    min_seconds: float = 30.0,
) -> list[tuple[float, float]]:
    """Cut `duration` seconds into pieces no longer than `max_seconds`, cutting in quiet gaps.

    For each piece the cut goes in a quiet gap between `min_seconds` and
    `max_seconds` after the piece start. Wide gaps beat narrow ones: a
    half-second breath inside a sentence is also "quiet", but a multi-second
    silence is a real boundary, so among the gaps in the window only those at
    least 70% as wide as the widest are eligible, and the *latest* of those
    wins (later cut = longer piece = fewer boundaries). The cut lands in the
    middle of the chosen gap. If the window holds no gap at all the cut is a
    hard cut at `max_seconds`, which can split a word; callers should treat it
    as a last resort. ``max_seconds <= 0`` returns a single piece.
    """
    if max_seconds <= 0 or duration <= max_seconds:
        return [(0.0, float(duration))]
    pieces: list[tuple[float, float]] = []
    pos = 0.0
    while duration - pos > max_seconds:
        window = [(a, b) for a, b in quiet if pos + min_seconds <= (a + b) / 2.0 <= pos + max_seconds]
        if window:
            widest = max(b - a for a, b in window)
            eligible = [(a, b) for a, b in window if b - a >= 0.7 * widest]
            a, b = max(eligible, key=lambda g: g[0])
            cut = (a + b) / 2.0
        else:
            cut = pos + max_seconds
        pieces.append((pos, cut))
        pos = cut
    pieces.append((pos, float(duration)))
    return pieces
