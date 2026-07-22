# Issue #002: `models_root()` silently split dev weights across two locations

**Status:** Fixed (`src/config.py`, `explore/vibevoice` branch)
**Found:** 2026-07-21/22, chasing 10 pre-existing "real synthesis" test failures while trying to
get the suite closer to 100% pass.
**Scope:** `src/config.py`, `tests/conftest.py`, `tests/test_config.py`

---

## Symptom

`tests/test_chatterbox.py`, `test_f5tts.py`, `test_piper.py`, `test_outetts.py`'s real-synthesis
tests failed with `synthesize() returned None` or similar — but their weights were plainly sitting
on disk under `python_app/.models/ml/<engine>/`, multiple GB each, clearly downloaded at some point.

## Cause

`models_root()`'s previous dev-mode resolution:

```python
prod = app_data_dir() / ".models"   # %LOCALAPPDATA%\com.alientech.alienvox\.models
if prod.exists():
    return prod
return Path(__file__).resolve().parents[1] / ".models"   # <repo>/python_app/.models
```

`%LOCALAPPDATA%\com.alientech.alienvox\.models` already existed on the dev machine (from earlier,
unrelated work — likely earlier installer/portable-build testing in this same long session,
predating today's changes). Because it existed, `models_root()` **always** returned the AppData
path for every dev-mode call — silently ignoring `python_app/.models`, where six engines' weights
had already been correctly downloaded in earlier sessions.

`tests/conftest.py`'s `requires_weights()` skip-gate compounded this: it hardcoded a check against
`python_app/.models` directly rather than calling the real `models_root()`, so it correctly
reported "weights present" (they were, at that path) — while the actual engine code, calling the
real `models_root()`, looked in the empty AppData directory and legitimately found nothing. Tests
ran for real (not skipped) and failed for a reason that had nothing to do with the engine code
itself.

VibeVoice's own weights ended up split across *both* locations during today's work, for the same
reason — whichever one happened to exist at the moment a given script ran.

## Fix

**Hard rule, explicitly requested and non-negotiable:** dev mode always uses
`<repo>/python_app/.models`, unconditionally — the `app_data_dir().exists()` check is removed
entirely from the dev path. Frozen/installed builds are unaffected — they still always use
`%LOCALAPPDATA%\com.alientech.alienvox\.models` (portable installs may sit on read-only/removable
media, so that side of the rule stays as-is).

- `src/config.py`'s `models_root()` — removed the `prod.exists()` branch from dev-mode resolution.
- `tests/conftest.py`'s `_real_models_root()` — now calls the real `src.config.models_root()`
  instead of hardcoding a path guess, so test gating can never diverge from what the app itself
  does again.
- `tests/test_config.py` — added `test_models_root_dev_ignores_app_data_dir_even_if_it_exists`,
  proving the hard rule holds even when the app-data directory is present and non-empty.
- Consolidated all orphaned weights (chatterbox, dia, f5tts, kokoro, outetts, piper — ~40GB total,
  moved not copied, same drive so effectively instant) from the AppData location back into
  `python_app/.models`, and removed the now-empty AppData `.models` directory on this dev machine.

**Result:** full test suite went from 10 failures / 372 passed to **0 failures / 386 passed** —
every one of those 10 was this bug, not a real engine defect.
