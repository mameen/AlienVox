"""Concrete engines supported by this self-contained MCP package.

Kokoro, Piper, and Supertonic 3 are available. Kokoro is the current default;
the Windows SAPI adapter is registered on Windows.

To add a new engine:
1. Create `engines/<name>.py`, subclass `..base.TtsEngine`, implement
   `list_voices`/`speak`/`stop` at minimum (see `kokoro.py` for the full
   reference shape, including `synthesize()` for raw-audio capture).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
The MCP server registers each engine in its vendored alienvox_tts package.
"""
from .kokoro import KokoroEngine
from .piper import PiperEngine
from .supertonic3 import Supertonic3Engine
try:
    from .sapi import SapiEngine
except ImportError:
    SapiEngine = None

__all__ = ["KokoroEngine", "PiperEngine", "Supertonic3Engine", "SapiEngine"]
