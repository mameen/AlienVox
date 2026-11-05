# alienvox_tts

A standalone, reusable, OOP Python TTS SDK — extracted from the [AlienVox](../python_app) desktop
app as a **copy**, not a refactor. This library has zero dependency on `python_app`'s package,
config system, or `stacks.yaml`; it's meant to be imported from anywhere in this repo (the
[`alien_vox` Claude Skill](../.agents/SKILLS/alien_vox/), [`python_mcp_server`](../python_mcp_server/),
or your own scripts) without any packaging or install step — just add this directory to `sys.path`,
or `pip install -e .` if you want it importable from a venv properly.

See [`docs/20260816_agentic_requiremetns_and_plan.md`](../docs/20260816_agentic_requiremetns_and_plan.md)
for the full background and scope decisions behind this library's existence.

## Install

```bat
cd python_lib
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick start

```python
from alienvox_tts import synthesize
import soundfile as sf

audio, sample_rate = synthesize("Hello, world!")   # Piper, Amy Medium, CPU
sf.write("out.wav", audio, sample_rate)
```

Or play directly through local speakers:

```python
from alienvox_tts import speak
speak("Hello, world!")   # blocks until playback finishes
```

Pick a different voice, or force CPU/GPU:

```python
from alienvox_tts import synthesize, select_device

audio, sr = synthesize("Hi!", voice="bm_george")                    # British M · George
audio, sr = synthesize("Hi!", rate=5, volume=80)                     # faster, quieter
device = select_device(prefer="cpu")                                  # "cpu" always
```

## What's included

- **`alienvox_tts.base`** — `TtsEngine` ABC, `Voice`, `SpeakParams` — the same contract every
  engine in `python_app` follows, copied out and documented inline.
- **`alienvox_tts.device`** — `select_device()`/`cuda_available()` — real CUDA detection (checks
  `device_count() > 0`, not just `is_available()`, which can be misleadingly true with zero
  visible devices).
- **`alienvox_tts.audio`** — `play_audio()`/`stop_playback()` — shared playback via `sounddevice`,
  including a real WASAPI hardware-buffer-tail fix already found and shipped in the app.
- **`alienvox_tts.engines.piper`** ? `PiperEngine`, the current trial default (CPU-only ONNX inference).
- **`alienvox_tts.engines.piper`** - `PiperEngine`, current trial default; CPU-only ONNX inference.
- **`alienvox_tts.engines.kokoro`** - `KokoroEngine`, former overall quality favorite. Kokoro-82M (Apache 2.0), via PyPI; downloads ~300 MB on first use. Seven voices; `af_heart` is its default voice.
- **`alienvox_tts.engines.supertonic3`** - multilingual ONNX CPU engine with 31 language options.

## Available engines

`python_app` has 9 engines total. This library ships Kokoro, Piper, and Supertonic 3; Piper is the current trial default. See `alienvox_tts/engines/__init__.py` for extension steps.

## Testing

```bat
python -m pytest tests/ -v
```

Real synthesis, no mocking (matches `python_app`'s own testing philosophy — see its
`.agents/SKILLS/testing/SKILL.md`). Skips gracefully (not a failure) if `kokoro`/`torch` aren't
installed in the current environment.

## License

Kokoro-82M's weights and the `kokoro` package are Apache 2.0. This library's own code follows the
parent repo's [LICENSE](../LICENSE) (MIT).
