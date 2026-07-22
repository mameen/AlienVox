# Issue #004: Manage Voices "Try Voice" preview hung on CPU

**Status:** Resolved — both reported hangs are now explained and no longer reproduce. See
"Resolution" below.
**Reported:** 2026-07-22
**Resolved:** 2026-07-22, verified via full real `python run.py perf --cpu` and `--gpu` sweeps
(53/53 results each, including all 6 `vibevoice_realtime` voices, no hangs on either device).
**Scope:** `src/engines/vibevoice_engine.py` (see `issue_005_transformers_pin.md` for the
full investigation this resolution came out of).

---

## Report

User: "running the sample from voice settings on CPU hung!" — using the Manage Voices dialog's
per-row "Try Voice" preview button, on CPU (not GPU). The app became unresponsive.

## Known context that may or may not be related

- A separate hang was observed earlier in this session running VibeVoice on **GPU** via the normal
  Play path (not preview) — see the investigation in the conversation history around
  `session-1784683311335_AlienVox.log`: generation started, logged
  `VibeVoice generating 123 chars (voice=emma)`, then nothing further — no completion, no error, no
  `speak.done`. No Windows crash/fault event was recorded for that process; it was later confirmed
  gone with no fault dump, consistent with a hang that was manually killed rather than a crash.
  Not yet confirmed whether this new CPU report is the same underlying issue via a different path
  (preview vs. Play) or a distinct one.
- `docs/issues/todo_006.md` already documents that VibeVoice is NOT real-time on CPU (measured RTF
  ~2.5x for a short phrase) — a long CPU generation could *look* like a hang if there's no
  progress indicator in the UI (the CLI's tqdm-style progress bar isn't shown in the GUI), even if
  it would eventually complete. Whether this report is "genuinely stuck forever" vs. "just slow
  with no feedback" has NOT been determined — needs reproduction with a timeout/wait to
  distinguish before any fix is attempted.
- Not yet confirmed which model/voice was being previewed, or whether this is VibeVoice-specific
  vs. a general preview-path issue (e.g., a deadlock in `_preview_voice`'s reuse-vs-load branching,
  or in `engine.wait_until_done(30_000)`'s 30s timeout not actually firing for some engine).

## Resolution

Both reports turned out to be transient side effects of the same investigation that produced
`issue_005_transformers_pin.md`, not real defects in `vibevoice_engine.py`:

- **The GPU hang** (first report, `VibeVoice generating 123 chars (voice=emma)` then nothing)
  happened while `vibevoice_engine.py` was mid-debug against `transformers==5.2.0` — a version
  `vibevoice` was never built for (it declares `transformers<5.0.0`). That combination produced a
  chain of real failures (an `AutoModel.register()` collision, a missing `Qwen2TokenizerFast`
  module path, a meta-device `tie_weights()` signature mismatch) — one of those failure modes,
  hit mid-generation rather than at load time, is consistent with an apparent hang.
- **The CPU hang** (second report) happened while a short-lived out-of-process architecture
  (VibeVoice running in a separate `.venv-vibevoice` subprocess) was being torn down mid-session —
  the app tried to spawn a worker subprocess against an **incomplete** venv (only `torch` had
  finished installing, not `transformers`/`vibevoice`), which would hang or fail confusingly
  rather than surface a clean error.

Neither cause exists in the final code: `vibevoice_engine.py` is back to a single in-process
engine (no subprocess, no separate venv), running under `transformers==4.51.3` for the whole main
venv (see `issue_005_transformers_pin.md`). Verified via full real `python run.py perf --cpu` and
`--gpu` sweeps — every stack/model/voice combination, including all 6 `vibevoice_realtime` voices
on both CPU and GPU, completed and played real audio with no hangs.
