"""Session-scoped fixtures shared across all tests."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# All ML model weight subdirs declared in stacks.yaml
_ALL_ML_MODELS = [
    "ml/kokoro",
    "ml/piper",
    "ml/chatterbox",
    "ml/dia",
    "ml/f5tts",
    "ml/outetts",
]


@pytest.fixture(scope="session")
def stacks_yaml() -> Path:
    """Real fixture stacks.yaml — mirrors production structure."""
    return FIXTURES_DIR / "stacks.yaml"


@pytest.fixture(scope="session")
def models_root(tmp_path_factory) -> Path:
    """Empty models root — no weights present by default.

    Tests that need weights present should create the subpath themselves.
    """
    return tmp_path_factory.mktemp("models")


@pytest.fixture(scope="session")
def models_root_with_weights(tmp_path_factory) -> Path:
    """Models root where ALL ML model weight directories exist.

    Empty dirs simulate installed weights for every model in stacks.yaml.
    """
    mr = tmp_path_factory.mktemp("models_with_weights")
    for subpath in _ALL_ML_MODELS:
        (mr / subpath).mkdir(parents=True)
    return mr


@pytest.fixture(scope="session")
def user_yaml(tmp_path_factory) -> Path:
    """Copy the fixture user.yaml into a temp dir so tests can read it."""
    tmp = tmp_path_factory.mktemp("user")
    src = FIXTURES_DIR / "user.yaml"
    dst = tmp / "user.yaml"
    dst.write_bytes(src.read_bytes())
    return dst
