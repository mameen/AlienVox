"""Concrete TtsEngine implementations.

Only `kokoro` ships in this version of the library — see the repo's
`docs/20260816_agentic_requiremetns_and_plan.md` for why (Kokoro is the
confirmed default and the simplest engine to extract cleanly; the other 8
engines in `python_app/src/engines/` are a documented future addition, not
implemented here yet).

To add a new engine:
1. Create `engines/<name>.py`, subclass `..base.TtsEngine`, implement
   `list_voices`/`speak`/`stop` at minimum (see `kokoro.py` for the full
   reference shape, including `synthesize()` for raw-audio capture).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
No other file needs to change — `synthesize()`, the skill's `speak.py`, and
the MCP server's `speak_text` tool all work with any registered engine.
"""
from .kokoro import KokoroEngine

__all__ = ["KokoroEngine"]
