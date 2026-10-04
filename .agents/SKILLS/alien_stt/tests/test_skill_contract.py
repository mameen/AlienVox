"""The authoring checklist, executed. These checks need no ffmpeg and no model."""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from conftest import SKILL_ROOT

SKILL_MD = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def _frontmatter() -> dict[str, str]:
    block = SKILL_MD.split("---", 2)[1]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        m = re.match(r"^([a-z-]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def test_name_matches_folder_and_is_valid():
    name = _frontmatter()["name"]
    assert name == SKILL_ROOT.name
    assert re.fullmatch(r"[a-z0-9_-]{1,64}", name)


def test_description_says_what_and_when_within_limit():
    desc = _frontmatter()["description"]
    assert 0 < len(desc) <= 1024
    assert "Use when" in desc and "Not for" in desc


def test_version_follows_major_minor_stamp():
    assert re.search(r'^\s+version: "\d+\.\d+\.\d{14}"$', SKILL_MD.split("---", 2)[1], re.MULTILINE)


def test_skill_md_is_lean():
    assert len(SKILL_MD.splitlines()) < 500


def test_every_local_link_exists():
    links = re.findall(r"\]\(([^)#\s]+)\)", SKILL_MD)
    local = [l for l in links if not re.match(r"^[a-z]+:", l)]
    assert local, "SKILL.md should link its resources"
    missing = [l for l in local if not (SKILL_ROOT / l).exists()]
    assert not missing, f"broken links: {missing}"


def test_no_absolute_paths_or_personal_markers_in_shipped_text():
    pattern = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\|/Users/|/home/\w+|@[\w-]+\.(com|org|net)\b")
    offenders = []
    for path in SKILL_ROOT.rglob("*"):
        if (not path.is_file() or path.suffix not in {".py", ".md", ".txt", ".json"}
                or any(p in {".venv", "__pycache__", ".build", ".pytest_cache"} for p in path.relative_to(SKILL_ROOT).parts)
                or path.name == "test_skill_contract.py"):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and "environment variable" not in line:
                offenders.append(f"{path.relative_to(SKILL_ROOT)}:{n}: {line.strip()[:80]}")
    assert not offenders, "\n".join(offenders)


def test_jobs_are_stated_and_boundary_named():
    assert "## Jobs to be Done" in SKILL_MD and "It does not" in SKILL_MD


@pytest.mark.parametrize("script", sorted(p.name for p in (SKILL_ROOT / "scripts").glob("*.py")))
def test_every_script_answers_help(script):
    proc = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / script), "--help"], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0 and "usage:" in proc.stdout.lower()


def test_importing_the_library_does_not_import_torch():
    code = "import sys; sys.path.insert(0, %r); import alienstt; print('torch' in sys.modules)" % str(SKILL_ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert out == "False"
