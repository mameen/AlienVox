"""End-to-end tests of the scripts as a user runs them: real processes, real files, real exit codes."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import SKILL_ROOT, requires_ffmpeg, requires_model

SCRIPTS = SKILL_ROOT / "scripts"


def run(script: str, *args, check=True):
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    if check and proc.returncode != 0:
        pytest.fail(f"{script} exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return proc


@requires_ffmpeg
def test_probe_text_and_json(sample_wav):
    assert "pcm_s16le" in run("probe_audio.py", sample_wav).stdout
    assert json.loads(run("probe_audio.py", sample_wav, "--json").stdout)[0]["sample_rate"] == 24000


@requires_ffmpeg
def test_probe_exit_code_on_bad_file(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"nope")
    assert run("probe_audio.py", bad, check=False).returncode == 1


@requires_ffmpeg
def test_convert_default_mp3_and_refuses_overwrite(sample_wav, tmp_path):
    src = tmp_path / "voice.wav"
    src.write_bytes(sample_wav.read_bytes())
    run("convert_audio.py", src)
    assert (tmp_path / "voice.mp3").exists()
    again = run("convert_audio.py", src, check=False)
    assert again.returncode == 1 and "exists" in again.stderr
    assert run("convert_audio.py", src, "--overwrite").returncode == 0


@requires_ffmpeg
def test_split_dry_run_then_split_and_manifest(gapped_wav, tmp_path):
    base = ["--segment-seconds", "12", "--min-seconds", "3"]
    plan = run("split_audio.py", gapped_wav, *base, "--dry-run").stdout
    assert "piece(s)" in plan and not list(tmp_path.glob("*.part*"))
    out = tmp_path / "parts"
    run("split_audio.py", gapped_wav, *base, "--out", out)
    parts = sorted(out.glob("*.part*.wav"))
    manifest = json.loads((out / "gapped.parts.json").read_text(encoding="utf-8"))
    assert len(parts) == len(manifest["parts"]) >= 2
    assert manifest["parts"][0]["start"] == 0.0 and manifest["parts"][1]["start"] > 5
    assert run("split_audio.py", gapped_wav, *base, "--out", out, check=False).returncode == 1   # parts exist


@requires_model
def test_transcribe_skips_existing_and_overwrite_redoes(sample_wav, tmp_path):
    out = tmp_path / "o"
    args = ["--model", "turbo", "--out", out, "--format", "md,json,srt"]
    first = run("transcribe.py", sample_wav, *args, "--lang", "en", "--log-dir", tmp_path / "log")
    assert "1 transcribed" in first.stdout
    assert {p.name for p in out.iterdir()} == {"sample_speech.transcript.md", "sample_speech.json", "sample_speech.srt"}
    log = next((tmp_path / "log").glob("transcribe-*.jsonl")).read_text(encoding="utf-8")
    assert "item_complete" in log and "Welcome" not in log           # events carry no transcript text
    assert "0 transcribed, 1 skipped" in run("transcribe.py", sample_wav, *args).stdout
    assert "1 transcribed" in run("transcribe.py", sample_wav, *args, "--lang", "en", "--overwrite").stdout


@requires_model
def test_split_transcribe_merge_search_render(gapped_wav, tmp_path):
    parts = tmp_path / "parts"
    run("split_audio.py", gapped_wav, "--segment-seconds", "12", "--min-seconds", "3", "--out", parts)
    run("transcribe.py", parts, "--model", "turbo", "--lang", "en", "--format", "json")
    merged = tmp_path / "whole.json"
    run("merge_transcripts.py", "--manifest", parts / "gapped.parts.json", *sorted(parts.glob("*.part??.json")), "--out", merged)
    t = json.loads(merged.read_text(encoding="utf-8"))
    assert sum("welcome" in s["text"].lower() for s in t["segments"]) == 3
    starts = [s["start"] for s in t["segments"]]
    assert starts == sorted(starts) and starts[-1] > 10 and any("merged from" in w for w in t["warnings"])
    assert run("find_in_transcript.py", "performance", merged).returncode == 0
    assert run("find_in_transcript.py", "zebra", merged, check=False).returncode == 1
    run("render_transcript.py", merged, "--format", "srt,vtt")
    assert (tmp_path / "whole.srt").exists() and (tmp_path / "whole.vtt").exists()


def test_transcribe_dry_run_loads_nothing(sample_wav):
    proc = run("transcribe.py", sample_wav, "--dry-run")
    assert "would transcribe" in proc.stdout and "dry run" in proc.stdout


def test_transcribe_rejects_bad_format_and_missing_input(tmp_path):
    assert run("transcribe.py", tmp_path, "--format", "pdf", check=False).returncode == 2
    assert run("transcribe.py", tmp_path / "nothing.mp3", check=False).returncode == 1


def test_check_setup_json_shape():
    data = json.loads(run("check_setup.py", "--json", check=False).stdout)
    assert {"ready", "checks"} <= data.keys()
    assert {c["name"] for c in data["checks"]} >= {"python", "ffmpeg", "torch", "model cache"}
