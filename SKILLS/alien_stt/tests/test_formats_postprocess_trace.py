"""Tests for formats, postprocess and trace. A Transcript is plain data, so building one by hand is not mocking."""
from __future__ import annotations

import json

import pytest

from alienstt import (RunLog, Segment, Transcript, clean_segments, load_transcript, new_run_id, normalize_for_search,
                      parse_formats, render, to_paragraphs, write_outputs)
from alienstt.formats import clock
from alienstt.postprocess import shift


@pytest.fixture()
def t():
    return Transcript(
        source="talk.mp3", duration=75.0, language="ar", language_probability=0.97, model="m", engine="whisper",
        device="cpu", created="20261003120000",
        segments=[Segment(0.0, 4.5, "مرحبا بكم"), Segment(5.0, 9.0, "Second line"), Segment(20.0, 24.25, "After a pause")],
    )


def test_clock_formats():
    assert clock(65) == "01:05" and clock(3725) == "1:02:05"
    assert clock(1.5, millis=True) == "00:00:01,500"
    assert clock(1.5, millis=True, dot=True) == "00:00:01.500"
    assert clock(59.9996, millis=True) == "00:01:00,000"             # rounding carries into the next second


def test_srt_and_vtt_structure(t):
    srt = render(t, "srt")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:04,500\nمرحبا بكم")
    assert "3\n00:00:20,000 --> 00:00:24,250" in srt
    assert render(t, "vtt").startswith("WEBVTT\n\n00:00:00.000 --> 00:00:04.500")


def test_md_carries_provenance_and_notice(t):
    md = render(t, "md")
    for needle in ("# Transcript: talk.mp3", "Model: `m` (whisper, cpu)", "97% confidence", "2026-10-03", "automatic draft", "[00:20] After a pause"):
        assert needle in md


def test_txt_breaks_paragraphs_on_pauses(t):
    assert render(t, "txt").strip().split("\n\n") == ["مرحبا بكم Second line", "After a pause"]


def test_tsv_is_tab_separated(t):
    rows = render(t, "tsv").splitlines()
    assert rows[0] == "start\tend\ttext" and rows[1] == "0.00\t4.50\tمرحبا بكم"


def test_json_round_trip_is_lossless(t, tmp_path):
    written, _ = write_outputs(t, tmp_path, "talk", ["json"])
    assert load_transcript(written[0]).to_dict() == t.to_dict()
    assert json.loads(written[0].read_text(encoding="utf-8"))["text"].startswith("مرحبا")


def test_write_outputs_skips_existing_unless_overwrite(t, tmp_path):
    w1, s1 = write_outputs(t, tmp_path, "talk", ["srt"], overwrite=False)
    w2, s2 = write_outputs(t, tmp_path, "talk", ["srt"], overwrite=False)
    assert (len(w1), len(s1), len(w2), len(s2)) == (1, 0, 0, 1)
    w3, _ = write_outputs(t, tmp_path, "talk", ["srt"], overwrite=True)
    assert len(w3) == 1 and not list(tmp_path.glob("*.partial"))


def test_files_are_utf8_without_bom(t, tmp_path):
    p, _ = write_outputs(t, tmp_path, "talk", ["txt"])
    assert not p[0].read_bytes().startswith(b"\xef\xbb\xbf")
    assert "مرحبا" in p[0].read_text(encoding="utf-8")


def test_parse_formats_accepts_all_and_rejects_typos():
    assert parse_formats("md, SRT") == ["md", "srt"]
    assert "json" in parse_formats("all")
    with pytest.raises(ValueError, match="unknown format"):
        parse_formats("md,pdf")


def test_clean_segments_drops_empty_and_runaway_repeats():
    segs = [Segment(0, 1, "Thanks."), Segment(1, 2, "Thanks."), Segment(2, 3, "thanks."), Segment(3, 4, "  "), Segment(4, 5, "Real.")]
    assert [s.text for s in clean_segments(segs)] == ["Thanks.", "Thanks.", "Real."]   # third repeat and the empty one dropped


def test_clean_segments_repairs_times():
    out = clean_segments([Segment(5, 6, "a"), Segment(3, 2, "b")])
    assert out[1].start >= out[0].start and out[1].end >= out[1].start


def test_drop_segments_in_silence_keeps_speech_only():
    from alienstt.postprocess import drop_segments_in_silence
    segs = [Segment(0, 2, "speech"), Segment(10, 12, "invented"), Segment(4, 8, "half")]
    kept, dropped = drop_segments_in_silence(segs, [(9.0, 15.0), (5.0, 6.0)])
    assert dropped == 1 and [s.text for s in kept] == ["speech", "half"]


def test_shift_moves_times_not_text():
    out = shift([Segment(1, 2, "x")], 10)
    assert (out[0].start, out[0].end, out[0].text) == (11, 12, "x")


def test_to_paragraphs_gap():
    segs = [Segment(0, 1, "a"), Segment(1.2, 2, "b"), Segment(9, 10, "c")]
    assert to_paragraphs(segs, gap=1.5) == ["a b", "c"]


def test_normalize_for_search_folds_marks_case_and_tatweel():
    assert normalize_for_search("Café") == "cafe"
    assert normalize_for_search("بِسْمِ اللَّهِ") == normalize_for_search("بسم الله")
    assert normalize_for_search("كــتاب") == normalize_for_search("كتاب")


def test_runlog_writes_jsonl_without_content_and_summarises(tmp_path):
    log = RunLog("transcribe", tmp_path, quiet=True)
    assert log.run_id.startswith("transcribe-") and len(log.run_id.split("-")[1]) == 14
    log.event("run_started", model="m")
    log.event("item_complete", item="a.mp3")
    log.event("item_failed", level="ERROR", item="b.mp3", error="boom")
    log.output(tmp_path / "x.md")
    lines = [json.loads(x) for x in log.path.read_text(encoding="utf-8").splitlines()]
    assert [x["event"] for x in lines] == ["run_started", "item_complete", "item_failed"]
    assert all(x["run_id"] == log.run_id and x["ts"].endswith("Z") for x in lines)
    s = log.summary()
    assert (s["complete"], s["failed"], s["skipped"]) == (1, 1, 0) and s["log"] == str(log.path)


def test_run_ids_are_unique():
    assert len({new_run_id("x") for _ in range(50)}) == 50
