# Kokoro-82M Voice Roster

The only engine this skill's vendored `alienvox_tts` currently ships (`engine=kokoro`, the default). All 7 voices load
from the same ~300MB model download — picking a different voice doesn't trigger a new download.

| Voice id | Label | Accent | Gender |
|---|---|---|---|
| `af_heart` | American F · Heart | American English | Female | **default**
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

This skill's vendored `alienvox_tts` ships Kokoro only for now (see the parent repo's
`docs/20260816_agentic_requiremetns_and_plan.md` for why). To add one:

1. Create `alienvox_tts/engines/<name>.py` (in this skill folder), subclass `TtsEngine` from
   `..base` (see `kokoro.py` for the full reference shape).
2. Register it in `alienvox_tts/__init__.py`'s `ENGINES` dict.
3. This skill's `speak.py --engine <name>` works with any registered engine automatically — no
   changes needed elsewhere. Note: `python_mcp_server`'s own `alienvox_tts` is a separate vendored
   copy (self-sufficiency over a shared dependency) — apply the same change there too if both
   should support the new engine.
