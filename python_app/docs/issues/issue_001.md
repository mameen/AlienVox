# Issue #001: VibeVoice GPU integration — 5 real device/dtype bugs found via real testing

**Status:** Fixed (`src/engines/vibevoice_engine.py`, `explore/vibevoice` branch)
**Found:** 2026-07-21, running the real test suite (`tests/test_vibevoice.py`) on a machine with
an actual CUDA GPU (RTX 4090) for the first time — every one of these was invisible on CPU-only
runs and only surfaced once `@requires_gpu`/GPU-path code actually executed for real. See
`testing/SKILL.md` §2.1 ("Device Testing — CPU Default, GPU Runs For Real When Present").
**Scope:** `src/engines/vibevoice_engine.py`, `tests/test_vibevoice.py`

---

## 1. `flash_attention_2` hardcoded on CUDA, `flash_attn` package not installed

**Symptom:** `ImportError: FlashAttention2 has been toggled on... the package flash_attn seems to
be not installed.` — model load failed outright on CUDA.

**Cause:** Copied the upstream demo script's device→attention-implementation mapping
(`cuda` → `flash_attention_2`) without noticing the demo script *also* has fallback error handling
for exactly this case, which the initial port omitted.

**Fix:** Wrap the `from_pretrained()` call in `try/except ImportError`, fall back to `sdpa` on
failure (matches upstream's own behavior) rather than hard-requiring a CUDA-only extra dependency
just to run on GPU at all.

---

## 2. Cached voice-prompt KV-cache never moved off CPU

**Symptom:** `RuntimeError: Expected all tensors to be on the same device, but found at least two
devices, cpu and cuda:0!` inside `torch.cat(...)` in `transformers/cache_utils.py`.

**Cause:** `cached_prompt` (the `.pt` preset-voice file) is always loaded via
`torch.load(..., map_location="cpu")` — correct, since a `.pt` file's origin device shouldn't
dictate where inference happens — but nothing then moved it to the model's actual device once the
model was on CUDA.

**Fix:** Added `_move_to_device()`, called on `cached_prompt` right after loading. Non-trivial
because `cached_prompt`'s structure isn't just tensors — see #3 and #4 below, both found while
fixing this one.

---

## 3. `_move_to_device` flattened HF `ModelOutput`-style dict-subclasses

**Symptom:** After fix #2's first pass: `AttributeError: 'dict' object has no attribute
'past_key_values'`.

**Cause:** `cached_prompt`'s leaf values (`lm`, `tts_lm`, etc.) are HF `ModelOutput`-like objects —
they subclass `dict` (so `isinstance(obj, dict)` matches) but rely on **attribute** access
(`.past_key_values`), not just key access. The first `_move_to_device` implementation used
`isinstance(obj, dict)` to decide "recurse and rebuild as a plain dict," which silently downgraded
these objects to genuine plain `dict`s, losing the attribute access `generate()` depends on.

**Fix:** Use `type(obj) is dict` (exact-type, not `isinstance`) to distinguish "genuinely plain
dict — flatten and recurse" from "dict-subclass with its own semantics — reconstruct via
`type(obj)(**moved_values)` instead."

---

## 4. HF `Cache` object has no working `.to()` in this transformers version

**Symptom:** After fix #3: back to the same `RuntimeError` as #2 (still a CPU/CUDA tensor mix),
this time originating deeper — inside `Cache.update()`'s `key_cache`/`value_cache` list handling.

**Cause:** The `Cache`-like object nested inside `cached_prompt` isn't a `dict`, `list`, or
`tuple`, and `getattr(obj, "to", None)` was falsy/ineffective for it in this transformers version
— so it fell straight through `_move_to_device` completely untouched, its internal
`key_cache`/`value_cache` tensor lists never moved.

**Fix:** Added a generic fallback: for any object that isn't a dict/list/tuple and doesn't have a
working `.to()`, walk `obj.__dict__` and recursively move+reassign every attribute in place. This
covers arbitrary custom classes (Cache objects included) without needing to special-case the exact
transformers version's `Cache` implementation.

---

## 5. `cached_prompt` reused across calls — `generate()` mutates it in place

**Symptom:** Second `synthesize()` call on the same voice within one process failed with a shape
mismatch inside `scaled_dot_product_attention` (`RuntimeError: The expanded size of the tensor
(118) must match the existing size (113)...`).

**Cause:** `generate()` appends each newly-generated token's key/value states into
`all_prefilled_outputs` **in place**. `VibeVoiceEngine._get_cached_prompt()` caches the loaded
`.pt` per voice in `self._prompt_cache` for reuse (avoiding re-loading the file every call) — but
passing that same cached, already-mutated-by-a-prior-call object straight into a second
`generate()` corrupts it (stale/grown cache from the first call collides with the second call's
fresh input length). The upstream demo script guards against exactly this with
`copy.deepcopy(all_prefilled_outputs)` before every `generate()` call — missed on the initial port.

**Fix:** `import copy; prefilled = copy.deepcopy(cached_prompt)` immediately before `generate()`,
passing `prefilled` (not the cached object itself) as `all_prefilled_outputs`. `self._prompt_cache`
now only ever holds the pristine, never-mutated loaded prompt.

---

## Related, but a test-design issue rather than an engine bug

`test_real_synthesis_volume_scaling`'s original form (mirroring `test_piper.py`/`test_f5tts.py`'s
pattern: two real `synthesize()` calls at different volumes, compare peak amplitude ratio) is
unsound for this engine — confirmed by real testing that VibeVoice's autoregressive GPU generation
isn't reproducible enough call-to-call (different generated-token counts, and once a *higher* peak
at the "lower" volume — proving the underlying content differed, not just its scale). Fixed by
extracting `apply_volume()` as a pure function (same pattern as `outetts_engine.py`'s
`resolve_speaker_name()`) and testing it directly/deterministically instead of inferring its
correctness from two independent nondeterministic real generations.
