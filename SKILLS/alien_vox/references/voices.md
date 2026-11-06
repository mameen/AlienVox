# Offline Voice Roster

## Piper voices (trial default engine)

Voice files are separate ONNX downloads. Current trial default: Amy Medium, CPU-only,
~63 MB on disk; it measured 0.421 s warm latency and 4.50 CPU-seconds for the canonical
123-character phrase, with a brief ~10.3-core burst. The Southern English Low alternative
measured 0.224 s and 2.53 CPU-seconds, with a brief ~11.5-core burst.
Piper voice files must be installed under the AlienVox models root (`ml/piper`);
set `ALIENVOX_MODELS_DIR` when using a different root.

| Voice id | Notes |
|---|---|
| `en_GB-southern_english_female-low` | Southern English (UK) female, low resource |
| `en_US-kathleen-low` | US English female, low resource |
| `en_US-lessac-medium` | US English male, medium |
| `en_US-amy-medium` | US English female, medium; current default |
| `en_US-ryan-high` | US English male, high quality |
| `en_GB-jenny_dioco-medium` | UK English female, medium |
| `en_GB-alan-medium` | UK English male, medium |

## Kokoro voices (former overall favorite)

Kokoro is a local alternative (`engine=kokoro`). All 7 voices load
from the same ~300MB model download — picking a different voice doesn't trigger a new download.

| Voice id | Label | Accent | Gender |
|---|---|---|---|
| `af_heart` | American F · Heart | American English | Female | available
| `af_bella` | American F · Bella | American English | Female |
| `af_nicole` | American F · Nicole | American English | Female |
| `am_adam` | American M · Adam | American English | Male |
| `am_michael` | American M · Michael | American English | Male |
| `bf_emma` | British F · Emma | British English | Female |
| `bm_george` | British M · George | British English | Male |

An unrecognized voice id silently falls back to `af_heart` (see `alienvox_tts/engines/kokoro.py`'s
`_synthesize_array` — logs a warning, doesn't raise) — the skill's operating procedure requires
reporting this fallback to the user explicitly rather than staying quiet about it.

## Controls

- **rate**: `-10` (0.5x speed) to `10` (2.0x speed), `0` = natural pace. Linear on each side of 0.
- **pitch**: accepted but ignored — Kokoro has no pitch control.
- **volume**: `0` (silent) to `100` (full), applied as a post-synthesis linear scale.

## Adding another engine

This skill's vendored `alienvox_tts` ships Piper, Kokoro, and `edge` (below) (see the parent repo's
`docs/20260816_agentic_requiremetns_and_plan.md` for why). To add one:

1. Create `alienvox_tts/engines/<name>.py` (in this skill folder), subclass `TtsEngine` from
   `..base` (see `kokoro.py` for the full reference shape).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
3. This skill's `speak.py --engine <name>` works with any registered engine automatically — no
   changes needed elsewhere. Note: `python_mcp_server`'s own `alienvox_tts` is a separate vendored
   copy (self-sufficiency over a shared dependency) — apply the same change there too if both
   should support the new engine.

## Edge voices (engine `edge`, networked)

Microsoft neural voices, id = service short name. Curated roster (any other valid short name is
passed to the service as-is; list them all with `edge_tts.list_voices()`):

| Voice id | Label |
|---|---|
| `ar-SA-HamedNeural` | Arabic (Saudi Arabia) M · Hamed — **edge default** |
| `ar-SA-ZariyahNeural` | Arabic (Saudi Arabia) F · Zariyah |
| `ar-EG-ShakirNeural` / `ar-EG-SalmaNeural` | Arabic (Egypt) M / F |
| `ar-AE-HamdanNeural` / `ar-AE-FatimaNeural` | Arabic (UAE) M / F |
| `en-US-AriaNeural` / `en-US-AndrewNeural` | English (US) F / M |
| `en-GB-SoniaNeural` / `en-GB-RyanNeural` | English (UK) F / M |

**Networked:** the text leaves the machine (Microsoft's online service), so it is opt-in and never the
default. Rate maps -10..10 to -50%..+100%; pitch maps to +/-5 Hz per step; volume is the same
post-synthesis scale. A malformed voice id raises; it does not fall back like Kokoro does. Output is
24 kHz mono, decoded from the service's MP3.
