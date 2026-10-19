"""Real ffmpeg tests for alienstt.audio: probe, decode, convert, collect, quiet gaps, chunk planning."""
from __future__ import annotations

import numpy as np
import pytest

from alienstt import audio as A
from conftest import requires_ffmpeg


# -- pure logic: no ffmpeg needed ------------------------------------------------
def test_plan_chunks_single_piece_when_short():
    assert A.plan_chunks(100.0, [], 600.0) == [(0.0, 100.0)]


def test_plan_chunks_zero_limit_disables_chunking():
    assert A.plan_chunks(5000.0, [], 0) == [(0.0, 5000.0)]


def test_plan_chunks_cuts_in_the_latest_gap_that_fits():
    quiet = [(50.0, 52.0), (95.0, 97.0), (150.0, 152.0)]
    pieces = A.plan_chunks(200.0, quiet, 100.0, min_seconds=30.0)
    assert pieces[0] == (0.0, 96.0)                       # middle of the 95-97 gap, the latest one under 100 s
    assert pieces[-1][1] == 200.0
    assert all(b - a <= 100.0 + 1e-6 for a, b in pieces)


def test_plan_chunks_prefers_a_wide_gap_over_a_late_narrow_one():
    quiet = [(40.0, 43.0), (95.0, 95.5)]                  # a 3 s silence early, a 0.5 s breath late
    assert A.plan_chunks(150.0, quiet, 100.0, min_seconds=30.0)[0] == (0.0, 41.5)


def test_plan_chunks_hard_cut_without_gaps():
    assert A.plan_chunks(250.0, [], 100.0) == [(0.0, 100.0), (100.0, 200.0), (200.0, 250.0)]


def _tone(seconds, sr=16000):
    return (0.3 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * sr)) / sr)).astype("float32")


def test_quiet_ranges_finds_the_silence_between_loud_parts():
    sr = 16000
    audio = np.concatenate([_tone(1), np.zeros(2 * sr, dtype="float32"), _tone(1)])
    ranges = A.quiet_ranges(audio, sr)
    assert len(ranges) == 1
    start, end = ranges[0]
    assert 0.9 <= start <= 1.1 and 2.9 <= end <= 3.1


def test_quiet_ranges_ignores_gaps_shorter_than_minimum():
    audio = np.concatenate([_tone(1), np.zeros(1600, dtype="float32"), _tone(1)])
    assert A.quiet_ranges(audio, 16000, min_silence=0.4) == []


def test_collect_inputs_dedupes_same_stem_and_reports_it(tmp_path):
    for name in ("a.ogg", "a.mp3", "b.wav", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    files, notes = A.collect_inputs([tmp_path])
    assert sorted(f.name for f in files) == ["a.mp3", "b.wav"]
    assert any("same name" in n for n in notes)


def test_collect_inputs_recursive_and_missing(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.flac").write_bytes(b"x")
    assert A.collect_inputs([tmp_path])[0] == []
    assert [f.name for f in A.collect_inputs([tmp_path], recursive=True)[0]] == ["c.flac"]
    assert "not found" in A.collect_inputs([tmp_path / "nope"])[1][0]


# -- real ffmpeg -----------------------------------------------------------------
@requires_ffmpeg
def test_probe_reports_real_properties(sample_wav):
    info = A.probe(sample_wav)
    assert info.audio_codec == "pcm_s16le"
    assert info.sample_rate == 24000 and info.channels == 1
    assert 5.0 < info.duration < 5.6
    assert info.has_video is False


@requires_ffmpeg
def test_decode_resamples_to_16k_mono(sample_wav):
    samples = A.decode(sample_wav)
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert abs(samples.size / 16000 - 5.275) < 0.05
    assert 0.01 < float(np.abs(samples).max()) <= 1.0     # real signal, not silence


@requires_ffmpeg
def test_decode_slice(sample_wav):
    assert abs(A.decode(sample_wav, start=1.0, duration=2.0).size / 16000 - 2.0) < 0.05


@requires_ffmpeg
@pytest.mark.parametrize("ext", [".mp3", ".flac", ".ogg", ".opus", ".m4a"])
def test_convert_round_trip_keeps_duration(sample_wav, tmp_path, ext):
    out = A.convert(sample_wav, tmp_path / f"x{ext}")
    assert out.exists() and out.stat().st_size > 1000
    assert abs(A.probe(out).duration - 5.275) < 0.3
    assert abs(A.decode(out).size / 16000 - 5.275) < 0.3


@requires_ffmpeg
def test_convert_refuses_to_overwrite_then_allows(sample_wav, tmp_path):
    dst = tmp_path / "x.mp3"
    A.convert(sample_wav, dst)
    with pytest.raises(A.AudioError, match="exists"):
        A.convert(sample_wav, dst)
    A.convert(sample_wav, dst, overwrite=True)
    assert not list(tmp_path.glob("*.partial*"))          # no temp files left behind


@requires_ffmpeg
def test_convert_resample_and_slice(sample_wav, tmp_path):
    out = A.convert(sample_wav, tmp_path / "s.wav", sample_rate=8000, channels=1, start=1.0, duration=2.0)
    info = A.probe(out)
    assert info.sample_rate == 8000 and abs(info.duration - 2.0) < 0.1


@requires_ffmpeg
def test_decode_missing_file_raises_audio_error(tmp_path):
    with pytest.raises(A.AudioError):
        A.decode(tmp_path / "missing.mp3")


@requires_ffmpeg
def test_probe_rejects_file_without_audio(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"this is not audio")
    with pytest.raises(A.AudioError):
        A.probe(bad)


@requires_ffmpeg
def test_gapped_speech_has_two_quiet_gaps(gapped_wav):
    ranges = A.quiet_ranges(A.decode(gapped_wav))
    assert len(ranges) >= 2
    longest = sorted(ranges, key=lambda r: r[1] - r[0], reverse=True)[:2]
    assert all(2.9 < b - a < 5.0 for a, b in longest)   # the 3 s we inserted, plus the sample's own lead/tail
