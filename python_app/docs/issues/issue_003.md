# Issue #003: Telemetry centralization refactor — 2 real bugs found via real testing

**Status:** Fixed (`src/control/app_controller.py`)
**Found:** 2026-07-22, while centralizing telemetry emission (per user request: the Manage Voices
dialog's "Try Voice" preview button wasn't emitting telemetry at all, unlike the normal Play/hotkey
path).
**Scope:** `src/control/app_controller.py`, `tests/test_app_controller.py`

---

## Background

`_preview_voice()` called `engine.speak()` directly, with zero telemetry — confirmed by the user's
own `--debug` log output showing no `speak.triggered`/`tts.first_audio`/etc. events for preview
clicks, only for normal speak. Fixed by extracting a shared `_run_engine_speak()` helper that both
`_speak_locked()` (normal path) and `_preview_voice()` now call, emitting the same 4 event types
(`speak.triggered`, `tts.first_audio`, `tts.playback_end`/`tts.error`, `speak.done`) tagged with a
`source` field ("speak" vs "preview") to distinguish them in the JSONL sink.

Two real regressions were introduced during this refactor and caught before merging, per
`testing/SKILL.md` §2.2's discipline (verify against real behavior, don't assume a refactor is
correct because it "looks" equivalent):

## 1. `text_chars`/`text_bytes` silently started measuring enhanced text, not original

**Symptom:** None visible in the existing test suite — all passed. Found only by manually tracing
field semantics: `text_chars` has always meant the pre-enhancement size (`enhanced_chars` is the
separate post-enhancement field, used to see how much enhancement actually changed).

**Cause:** The new shared `_run_engine_speak()` initially auto-computed `text_chars=len(text)` from
whatever `text` it was handed — but `_speak_locked()` passes the *enhanced* text to it (the text
that's actually spoken), not the original. Every existing test that checked debug/enhance fields
set `ctrl.engine = None` to avoid needing a real engine, which routes through a different fallback
branch that never had this bug — so nothing caught it.

**Fix:** Removed the auto-computation from `_run_engine_speak()` entirely — `text_chars`/
`text_bytes` (and every other `speak.triggered` field) must now be supplied explicitly by the
caller via `extra_triggered_fields`, since "what does text_chars mean" is caller-specific
(original size for the real speak path; `SAMPLE_TEXT` size for preview, which has no enhancement
concept at all).

**Caught by:** a new test, `test_speak_locked_text_chars_is_original_not_enhanced_when_engine_present`,
written specifically to keep the fake engine active (not `None`) — the one thing every prior test
avoided.

## 2. Duplicate-keyword `TypeError`, silently swallowed by a bare `except Exception`

**Symptom:** After fixing #1, the "no engine" fallback branch in `_speak_locked()` started passing
`text_chars`/`text_bytes` explicitly *and* via `**extra_fields` (which now also contains those
keys) — a `TypeError: got multiple values for keyword argument 'text_chars'`. This exception was
caught by `_speak_locked()`'s outer `except Exception`, which only called
`self.state.set_error(...)` with **no log line** — so five previously-passing tests started failing
with `IndexError`/`StopIteration` (zero telemetry events were ever emitted) and the actual cause
(a `TypeError`) was invisible without adding a print/log statement to find it.

**Fix:** Removed the now-redundant explicit `text_chars`/`text_bytes` keywords from that branch
(already present in `extra_fields`). Also added a `_log.error(...)` call to `_speak_locked()`'s
outer exception handler — a silent `except Exception` that only sets `AppState.error` (a UI-visible
field, not a log line) is a real diagnosability gap independent of this specific bug; it should
never be the *only* signal a real code defect produces.

## Verification

Full `tests/test_app_controller.py` suite: 29 passed (23 pre-existing + 6 new — 2 covering the
preview telemetry fix itself, 2 covering these two regressions, 2 more general coverage). Every
event field verified against real emitted telemetry (mocked `Telemetry.emit`, not mocked
`AppController` internals — the anti-mocking philosophy this whole investigation exists to prove
out).
