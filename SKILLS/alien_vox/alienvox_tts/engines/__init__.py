"""Concrete engines supported by this portable skill package.

Piper and Kokoro are local/offline engines. Edge uses Microsoft's network
service and remains opt-in. Piper is the current trial default.

To add a new engine:
1. Create `engines/<name>.py`, subclass `..base.TtsEngine`, implement
   `list_voices`/`speak`/`stop` at minimum (see `kokoro.py` for the full
   reference shape, including `synthesize()` for raw-audio capture).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
The MCP server maintains a separate vendored engine package.
"""
from .edge import EdgeEngine
from .kokoro import KokoroEngine
from .piper import PiperEngine

__all__ = ["EdgeEngine", "KokoroEngine", "PiperEngine"]
