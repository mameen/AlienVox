# alien_vox — AlienVox TTS Claude Code Skill

Speaks text aloud through the local speakers using AlienVox's Kokoro-82M TTS engine — local,
offline, no API keys. Default voice: `af_heart` ("American F · Heart"). Default device: CPU
(pass `--device gpu` to opt into CUDA if available).

**Fully self-sufficient**: `alienvox_tts` is vendored directly inside this folder
(`./alienvox_tts/`) — no sibling `../../../python_lib` dependency. Copy this skill folder alone to
a new machine/repo and it runs; see [`AGENTS.md`](AGENTS.md) for the checklist.

See [`SKILL.md`](SKILL.md) for the full skill definition (when/how an agent should use this).

## Install

```bat
cd .agents/SKILLS/alien_vox
python -m venv .venv
.venv\Scripts\activate
pip install -r scripts/requirements.txt
```

## Use

```bat
python scripts/speak.py "Text to speak here" [--voice af_heart] [--device cpu|gpu] [--no-play] [--out output.wav]
```

Plays through the local default audio device by default. See [`references/voices.md`](references/voices.md)
for the full 7-voice roster and controls (rate/pitch/volume).

## Test

```bat
python -m pytest tests/ -v
```

Real synthesis tests (anti-mocking philosophy — see `python_app`'s
`.agents/SKILLS/testing/SKILL.md` in this repo) — skip gracefully if `kokoro`/`torch` aren't
installed, real otherwise.

## Build for deployment

```bat
python build.py
```

Zips this skill folder (excluding `.venv/`, `__pycache__/`, `.build/`, and other dev-only files)
into `.build/alien_vox.zip` — a self-contained artifact that can be copied/shared and unzipped
elsewhere to run standalone.
