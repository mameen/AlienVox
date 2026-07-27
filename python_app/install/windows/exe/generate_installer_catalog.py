from __future__ import annotations

from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[3]
STACKS_PATH = ROOT / "stacks.yaml"
MANIFEST_PATH = ROOT / "install" / "assets" / "audio" / "manifest.yaml"
OUT_PATH = Path(__file__).with_name("installer_catalog.generated.iss")
SAMPLES_OUT_PATH = Path(__file__).with_name("installer_samples.generated.iss")


def esc(text: str) -> str:
    return text.replace("'", "''")


def human_size_mb(path: str) -> str:
    file_path = ROOT / "install" / "assets" / "audio" / path
    if not file_path.exists():
        return ""
    size_mb = file_path.stat().st_size / (1024 * 1024)
    return f"~{size_mb:.1f} MB"


def temp_alias(stack_id: str, model_id: str, voice_id: str) -> str:
    parts = [stack_id]
    if model_id:
        parts.append(model_id)
    if voice_id:
        parts.append(voice_id)
    return "sample_" + "_".join(parts) + ".mp3"


def main() -> int:
    stacks = yaml.safe_load(STACKS_PATH.read_text(encoding="utf-8"))["stacks"]
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))["samples"]
    sample_map = {(s["stack_id"], s["model_id"], s["voice_id"]): s["file"] for s in manifest}

    lines = []
    sample_lines = []
    for stack in stacks:
        lines.append(f"  AddCatalogItem(0, '{esc(stack['name'])}', '', '{esc(stack['id'])}', '', '', '');")
        for model in stack.get("models", []):
            model_size = f"~{model.get('approx_size_mb')} MB" if model.get("approx_size_mb") else ""
            lines.append(
                f"  AddCatalogItem(1, '  {esc(model['name'])}', '{esc(model_size)}', '{esc(stack['id'])}', '{esc(model['id'])}', '', '');"
            )
            for voice in model.get("voices", []):
                sample = sample_map.get((stack["id"], model["id"], voice["id"]), "")
                size = human_size_mb(sample) if sample else (f"~{voice['size_mb']} MB" if voice.get("size_mb") else "")
                alias = temp_alias(stack["id"], model["id"], voice["id"])
                if sample:
                    sample_lines.append(
                        f"Source: \"{{#DistDir}}\\_internal\\install\\assets\\audio\\{esc(sample)}\"; "
                        f"DestName: \"{esc(alias)}\"; Flags: dontcopy ignoreversion"
                    )
                lines.append(
                    f"  AddCatalogItem(2, '    {esc(voice['label'])}', '{esc(size)}', '{esc(stack['id'])}', '{esc(model['id'])}', '{esc(voice['id'])}', '{esc(alias)}');"
                )

    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    SAMPLES_OUT_PATH.write_text("\n".join(sample_lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {SAMPLES_OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
