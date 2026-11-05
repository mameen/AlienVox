"""Concrete TtsEngine implementations shipped by this standalone library.

The library currently includes Kokoro, Piper, and Supertonic 3. Piper is the
current default; the desktop and MCP server keep independent vendored copies
so each surface can run without depending on a sibling package.

To add a new engine:
1. Create `engines/<name>.py`, subclass `..base.TtsEngine`, implement
   `list_voices`/`speak`/`stop` at minimum (see `kokoro.py` for the full
   reference shape, including `synthesize()` for raw-audio capture).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
The skill and MCP server maintain their own copies of this engine registry.
"""
from .kokoro import KokoroEngine
from .piper import PiperEngine
from .supertonic3 import Supertonic3Engine
try:
    from .sapi import SapiEngine
except ImportError:
    SapiEngine = None

__all__ = ["KokoroEngine", "PiperEngine", "Supertonic3Engine", "SapiEngine"]
