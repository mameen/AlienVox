#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Engine registry: look an engine up by name, never import a concrete class elsewhere.

Adding an engine is two steps: write a class implementing `alienstt.base.SttEngine`
in a new module here, and add it to `ENGINES`. Nothing else in the library
changes. See docs/ROADMAP.md for engines that are intended but not built.
"""
from __future__ import annotations

from typing import Any

from ..base import SttEngine
from .whisper_hf import DEFAULT_MODEL, MODEL_ALIASES, WhisperHFEngine, resolve_model

#: name -> class. The only engine shipped today is Whisper through `transformers`.
ENGINES: dict[str, type[SttEngine]] = {"whisper": WhisperHFEngine}

DEFAULT_ENGINE = "whisper"


def get_engine(name: str = DEFAULT_ENGINE, **kwargs: Any) -> SttEngine:
    """Create an engine by registry name; keyword arguments go to its constructor.

    Raises `KeyError` listing the available names if `name` is unknown, so a
    typo in a script argument produces an actionable message.
    """
    try:
        cls = ENGINES[name]
    except KeyError:
        raise KeyError(f"unknown engine {name!r}; available: {', '.join(sorted(ENGINES))}") from None
    return cls(**kwargs)


__all__ = ["DEFAULT_ENGINE", "DEFAULT_MODEL", "ENGINES", "MODEL_ALIASES", "get_engine", "resolve_model"]
