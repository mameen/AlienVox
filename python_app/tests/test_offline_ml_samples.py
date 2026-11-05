"""Coverage for bundled offline previews of the lightweight ML catalogs."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_every_lightweight_voice_has_a_bundled_offline_sample():
    root = Path(__file__).parents[1]
    catalog = yaml.safe_load((root / "stacks.yaml").read_text(encoding="utf-8"))
    manifest = yaml.safe_load(
        (root / "install" / "assets" / "audio" / "manifest.yaml").read_text(encoding="utf-8")
    )
    expected_models = {"pockettts", "supertonic3", "moss_tts_nano"}
    models = {
        model["id"]: model
        for stack in catalog["stacks"] if stack["id"] == "ml"
        for model in stack.get("models", []) if model["id"] in expected_models
    }
    samples = {
        (sample["model_id"], sample["voice_id"]): sample["file"]
        for sample in manifest["samples"]
        if sample.get("stack_id") == "ml" and sample.get("model_id") in expected_models
    }

    assert set(models) == expected_models
    for model_id, model in models.items():
        for voice in model["voices"]:
            key = (model_id, voice["id"])
            assert key in samples, f"{model_id}/{voice['id']} is missing from the sample manifest"
            sample_path = root / "install" / "assets" / "audio" / samples[key]
            assert sample_path.is_file(), f"{model_id}/{voice['id']} sample is missing: {sample_path}"
            assert sample_path.stat().st_size > 1_000, f"{model_id}/{voice['id']} sample is empty"
