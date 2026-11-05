"""Real CPU-only benchmark for the developer's preferred offline voices.

Reads the canonical SAMPLE_TEXT from python_app/src/control/app_controller.py,
does one cold synthesis and three warm repetitions per voice, and writes a
JSON report plus WAV files. Requires local model weights; no model downloads.
"""
from __future__ import annotations

import ast
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import soundfile as sf

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[1]))
os.environ.setdefault("ALIENVOX_MODELS_DIR", str(ROOT / "python_app" / ".models"))

from alienvox_tts import SpeakParams, get_engine, list_voices


def canonical_phrase() -> str:
    source = ROOT / "python_app" / "src" / "control" / "app_controller.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SAMPLE_TEXT" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError(f"SAMPLE_TEXT not found in {source}")


PHRASE = canonical_phrase()
TOP_VOICES = [
    ("kokoro", "af_heart"), ("kokoro", "af_bella"), ("kokoro", "bf_emma"),
    ("kokoro", "am_adam"), ("kokoro", "bm_george"),
    ("supertonic3", "F1"), ("supertonic3", "F4"),
    ("piper", "en_US-lessac-medium"), ("piper", "en_US-amy-medium"),
    ("piper", "en_US-ryan-high"), ("piper", "en_US-kathleen-low"),
    ("piper", "en_GB-southern_english_female-low"), ("piper", "en_GB-jenny_dioco-medium"),
    ("sapi5", "MSTTS_V110_enGB_HazelM"), ("sapi5", "MSTTS_V110_enGB_SusanM"),
    ("sapi5", "TTS_MS_EN-US_ZIRA_11.0"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="report folder; defaults to a new timestamped folder")
    args = parser.parse_args()
    import torch
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    out_dir = args.output_dir or ROOT / "python_mcp_server" / "reports" / ("cpu-top-voices-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()
    results = []
    for engine_id, requested_voice in TOP_VOICES:
        row = {"engine": engine_id, "voice_requested": requested_voice, "device": "cpu", "phrase_chars": len(PHRASE), "runs": []}
        try:
            voices = list_voices(engine_id)
            voice = next((v.id for v in voices if v.id == requested_voice), None)
            if voice is None and engine_id.startswith("sapi"):
                voice = next((v.id for v in voices if requested_voice.casefold() in (v.id + " " + v.name).casefold()), None)
            if voice is None:
                raise LookupError("requested voice is not installed; available: " + ", ".join(v.name for v in voices))
            row["voice_id"] = voice
            synth = get_engine(engine_id, "cpu").synthesize
            for run_index in range(4):
                rss_before = proc.memory_info().rss
                cpu_before = proc.cpu_times().user + proc.cpu_times().system
                started = time.perf_counter()
                audio, sample_rate = synth(PHRASE, voice, SpeakParams())
                elapsed = time.perf_counter() - started
                cpu_after = proc.cpu_times().user + proc.cpu_times().system
                rss_after = proc.memory_info().rss
                duration = len(audio) / sample_rate
                run = {"run": "cold" if run_index == 0 else f"warm_{run_index}", "synthesis_seconds": round(elapsed, 4),
                       "audio_seconds": round(duration, 4), "real_time_factor": round(elapsed / duration, 4),
                       "process_cpu_seconds": round(cpu_after - cpu_before, 4),
                       "cpu_percent_one_core": round(100 * (cpu_after - cpu_before) / elapsed, 1) if elapsed else 0,
                       "rss_delta_mb": round((rss_after - rss_before) / 1048576, 2),
                       "rss_mb_after": round(rss_after / 1048576, 2), "sample_rate": int(sample_rate)}
                row["runs"].append(run)
                if run_index == 0:
                    safe_name = f"{engine_id}-{requested_voice}".replace("/", "_")
                    sf.write(out_dir / f"{safe_name}.wav", audio, sample_rate)
            warm = [r["synthesis_seconds"] for r in row["runs"][1:]]
            row["warm_median_seconds"] = round(statistics.median(warm), 4)
            row["status"] = "ok"
        except Exception as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {exc}")
        results.append(row)
        print(f"{engine_id}/{requested_voice}: {row['status']}" + (f" {row.get('warm_median_seconds')}s warm median" if row.get("status") == "ok" else f" — {row.get('error')}"))
    report = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "phrase_source": "python_app/src/control/app_controller.py:SAMPLE_TEXT", "phrase": PHRASE,
              "phrase_chars": len(PHRASE), "device": "CPU", "runs_per_voice": 4,
              "measurement_notes": "Cold first-use synthesis plus three warm calls; CPU percent is process CPU time divided by synthesis wall time (100% equals one fully occupied core). RSS is sampled immediately after synthesis, not peak memory. Sequential voices share a process, so RSS deltas include retained model state and are not isolated per-model memory estimates.",
              "results": results}
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    print(f"Successful voices: {sum(r['status'] == 'ok' for r in results)}/{len(results)}")
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
