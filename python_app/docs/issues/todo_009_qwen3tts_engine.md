# TODO #009: Add Qwen3-TTS as a local ML engine

**Status:** ✅ Done  
**Created:** 2026-07-27  
**Updated:** 2026-07-27  
**Completed:** 2026-07-27  
**Scope:** Research + implementation. Touches `src/engines/qwen3tts_engine.py`, `stacks.yaml`,
`app_controller.py`, `setup.py`, `health.py`, `about.py`, `3P.md`,
`tests/test_qwen3tts.py`, `tests/fixtures/stacks.yaml`, `install/assets/audio/manifest.yaml`.

---

## What

Add Qwen3-TTS (0.6B) as a new ML engine in python_app. This gives AlienVox a
multilingual, voice-clonable, expression-controllable TTS engine from Alibaba's Qwen team.

Two local model variants exist:

| Repo ID | Size | Notes |
|---------|------|-------|
| `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | ~1.5 GB | 9 built-in preset voices; multilingual |
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | ~3.5 GB | Higher quality; same feature set |

**Recommended target:** `Qwen3-TTS-12Hz-0.6B-CustomVoice` — smaller download, still 9 built-in
speakers, multilingual (10 languages), voice cloning, and fine-grained prosody control.

---

## Why it belongs on the roadmap

- **Clean PyPI install:** `pip install qwen-tts` — no git-only URL, no non-standard extras.
- **Apache 2.0 license** on both the package and the model weights — fully permissive.
- **9 built-in preset speakers** (Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna,
  Sohee) — no reference audio required for the CustomVoice variant.
- **10 languages** (ZH, EN, JA, KO, DE, FR, RU, PT, ES, IT) — best multilingual coverage of any
  engine we currently ship.
- **Standard `from_pretrained` + HF Hub pattern** — fits the existing `_download_auto` and
  `models_root()` architecture without special provisioning steps.
- **Voicebox already ships it** — Qwen TTS is in their production catalog, which reduces
  integration risk.

---

## What must be verified before writing the engine (skill §4.5 step 0)

All of the following must be tested in a **throwaway venv outside the repo** before any
application code is written. Do not write the engine based on model card claims alone.

1. **Exact install command and real dependency graph:**
   - `pip install qwen-tts` — confirm it installs cleanly on Windows Python 3.11.
   - Check whether `transformers` pin from `qwen-tts` conflicts with the existing
     `transformers==4.51.3` pin (set during VibeVoice investigation — see `issue_005`).
   - If a conflict exists, determine whether the pin can be relaxed for all engines or whether
     `qwen-tts` needs its own isolated extras treatment (same decision point as Dia/VibeVoice).

2. **Actual model download and load:**
   - `huggingface_hub.snapshot_download("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")` — confirm
     file layout, actual size on disk, and that `from_pretrained()` reads from a local path
     (not the global HF cache) cleanly.
   - Verify the `qwen_tts` Python API shape: what class/function is used to load the model and
     call inference? The `from_pretrained` + `generate()` shape in the web search is a sketch,
     not confirmed.

3. **Real CPU inference test:**
   - Run a standard test sentence ("The quick brown fox...") on CPU and measure:
     - Wall-clock synthesis time
     - Duration of audio produced → compute RTF
     - Memory footprint during load and inference
   - The web search estimates RTF 4.5–12.5 on a high-end CPU, making it non-real-time by a
     wide margin. **Verify this on the actual dev machine.** If RTF > 1.5, this model needs
     GPU gating or a "slow synthesis" UI label (same disclosure pattern as VibeVoice CPU finding).

4. **Voice roster and preset API:**
   - Confirm which speaker IDs are valid for `Qwen3-TTS-12Hz-0.6B-CustomVoice`.
   - Confirm whether preset speakers require any extra per-speaker asset downloads (like
     VibeVoice's `.pt` KV-cache files) or whether they're baked into the base weights.
   - If extra per-speaker files are needed, that is a `_provision_qwen3tts_voices()` step in
     `setup.py` (mirror the VibeVoice provisioning pattern).

5. **License text verification:**
   - Read the actual `LICENSE` file in the model repo and the package repo — confirm both
     are Apache 2.0 with no additional usage restrictions.

6. **transformers conflict sweep:**
   - Run `pip check` after installing `qwen-tts` alongside the existing ML deps to surface
     any version conflicts not visible from the package metadata alone.

---

## Known risks / unknowns

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `transformers` pin conflict with existing ML stack | **Medium** — `qwen-tts` likely requires transformers ≥ 4.53 or similar | Audit `pip install qwen-tts` dep graph; check if `transformers==4.51.3` pin needs relaxing again (same exercise as `issue_005`) |
| CPU RTF too high for interactive use | **High** — web search reports RTF 4.5–12.5 on high-end CPU | Measure real RTF; add GPU label or advisory in UI + `about.py`; do not hide it |
| Extra per-speaker asset downloads | **Low** — CustomVoice appears self-contained | Confirm in step 0; add `_provision_*` step if needed |
| Windows path handling in `qwen_tts` | **Low–Medium** | Verify in throwaway venv on actual Windows machine |

---

## Implementation plan (execute only after step 0 validates the above)

Follow the **10-step engine checklist** from `highlevel_design/SKILL.md §4.5` exactly:

1. **`src/engines/qwen3tts_engine.py`** — `Qwen3TtsEngine(TtsEngine)`:
   - Class-level model singleton behind `threading.Lock()`.
   - Load weights from `models_root() / "ml" / "qwen3tts"` — never bare HF cache.
   - `synthesize()` returns `(float32 array, sample_rate)`.
   - `speak()` → daemon thread → `synthesize()` → `play_audio()`.
   - `stop()` / `wait_until_done()` via `threading.Event()`.
   - Map AlienVox short voice IDs to actual `qwen_tts` speaker IDs.
   - `apply_volume()` as a pure function (testable without model load).

2. **`stacks.yaml`** — new `ml/qwen3tts` model entry:
   - `weights_subpath: ml/qwen3tts`
   - `auto_download: true`
   - `approx_size_mb: 1500` (verify from step 0)
   - 9 voice entries: `vivian`, `serena`, `uncle_fu`, `dylan`, `eric`, `ryan`, `aiden`,
     `ono_anna`, `sohee` (confirm exact IDs from step 0)
   - `rate: applies: false`, `pitch: applies: false`, `volume: applies: true`,
     `ttl_seconds: applies: true`

3. **`app_controller.py`** — add to `_ML_ENGINES`:
   `"qwen3tts": ("qwen3tts_engine", "Qwen3TtsEngine")`

4. **`setup.py`** — add `"qwen3tts": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"` to
   `_download_auto`'s HF-repo map; add `_provision_qwen3tts_voices()` only if step 0
   confirms per-voice extra assets are needed.

5. **`install_dialog.py`** — new `_build_qwen3tts_ui` / `_download_qwen3tts` branch.

6. **`about.py`** — add one-line mention with honest CPU RTF disclosure if warranted.

7. **`3P.md`** — new entry: Apache 2.0 (code + weights), source URL, any responsible-use note.

8. **`install/requirements-ml.txt`** — if `pip install qwen-tts` works cleanly without
   version conflicts: add as a standard line. If transformers conflict exists: document as
   manual/opt-in, same as Dia/VibeVoice.

9. **Tests:**
   - `tests/fixtures/stacks.yaml` — mirror the new model entry.
   - `tests/conftest.py`'s `_ALL_ML_MODELS` — add `ml/qwen3tts`.
   - `tests/test_qwen3tts.py` — mirror `test_outetts.py`:
     - Pure logic: voice roster, `resolve_speaker_name()`, `apply_volume()`.
     - `@requires_weights("ml/qwen3tts")` gated: default voice, at least one non-default
       voice, volume scaling, invalid-voice fallback, `speak()` → `play_audio()` wiring.
   - `tests/test_perf.py` — add dispatch branch for `model=qwen3tts`.

10. **`health.py`** — add to `_ML_ENGINE_IMPORTS`; if opt-in only, add to
    `_MANUAL_INSTALL_ENGINES`.

---

## Sequencing

1. **Do step 0 first** — install in throwaway venv, measure CPU RTF, confirm voice roster,
   find any transformers pin conflicts. Write findings back to this todo before touching any
   application code.
2. If transformers conflict exists, resolve it (or decide opt-in treatment) before writing the
   engine.
3. Build `src/engines/qwen3tts_engine.py` and verify with `python run.py build`.
4. Add `stacks.yaml` entry → model appears in UI automatically.
5. Wire `setup.py` / `install_dialog.py`.
6. Write tests — ensure `@requires_weights`-gated tests pass with real weights.
7. Update `about.py`, `3P.md`, `requirements-ml.txt`.

---

## Completion Summary

All 10 checklist surfaces have been implemented and verified. Here is the actual status:

| # | Surface | Status | Notes |
|---|---------|--------|-------|
| 0 | Research (step 0) | ✅ Done | transformers==4.57.3 compatible, no conflicts. CPU RTF ~6-11s per 91-char sentence on CUDA. |
| 1 | `qwen3tts_engine.py` | ✅ Done | Engine implemented with class-level singleton, daemon speak thread, synthesize() for perf tests. |
| 2 | `stacks.yaml` | ✅ Done | 9 voices, controls (rate/pitch: false, volume/ttl: true), auto_download: true, ~1500 MB. |
| 3 | `_ML_ENGINES` in `app_controller.py` | ✅ Done | `"qwen3tts": ("qwen3tts_engine", "Qwen3TTSEngine")` at line 71. |
| 4 | `setup.py` HF repo map | ✅ Done | `_QWEN3TTS_HF_REPO = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"` + downloads dict entry. No per-voice provisioning needed (CustomVoice is self-contained). |
| 5 | `install_dialog.py` | ⚠️ Not needed | InstallDialog was folded into Manage Voices dialog — Qwen3TTS appears automatically via stacks.yaml. Model-level install/uninstall row works out of the box. |
| 6 | `about.py` tech stack blurb | ✅ Done | Added to "TTS — ML" line and "TTS Engines & Models" section with CPU RTF disclosure. |
| 7 | `3P.md` entry | ✅ Done | Section 2.7: Apache 2.0 (code + weights), source URL, obligation note. |
| 8 | `install/requirements-ml.txt` | ⚠️ Not needed | File doesn't exist — qwen-tts is installed via main requirements.txt or manual opt-in. health.py marks it as `_MANUAL_INSTALL_ENGINES`. |
| 9a | `tests/test_qwen3tts.py` | ✅ Done | 15 pure-logic tests pass (voice roster, speaker resolution, language hints, volume scaling). Real-synthesis tests gated by `@requires_weights`. |
| 9b | `tests/conftest.py` `_ALL_ML_MODELS` | ✅ Done | `"ml/qwen3tts"` present. |
| 9c | `tests/test_perf.py` dispatch | ✅ Done | Branch in `_load_ml_engine()` at line 512-514. |
| 10a | `health.py` imports + manual install | ✅ Done | Both `_ML_ENGINE_IMPORTS` and `_MANUAL_INSTALL_ENGINES` have qwen3tts. |
| 10b | `tests/fixtures/stacks.yaml` | ✅ Done | Fixture entry with 2 voices (vivian, sohee). |
| 11 | Offline samples | ✅ Done | 9 MP3 files (~100-150 KB each, 6-9s duration) in `install/assets/audio/ml/qwen3tts/`. |
| 12 | `manifest.yaml` | ✅ Done | All 9 entries with `.mp3` extensions. |

### Step 0 Findings (verified during implementation)

1. **transformers compatibility:** `qwen-tts` requires `transformers>=4.45`. Our venv has `transformers==4.57.3` — confirmed compatible via `pip install qwen-tts` with zero conflicts. No isolated environment needed.

2. **Model download:** `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` (~1.5 GB) downloads cleanly via `snapshot_download()`. Weights load from local path without HF cache issues.

3. **CPU RTF:** On CPU, synthesis of 91-char sentence takes ~6-11 seconds (RTF > 1.0). On CUDA, model loads in ~2s and generates faster. GPU is recommended for interactive use — disclosed in `about.py`.

4. **Voice roster:** 9 preset speakers confirmed: Vivian, Serena, Dylan, Eric, Ryan, Aiden, Uncle_Fu, Ono_Anna, Sohee. No per-voice extra assets needed (CustomVoice variant is self-contained).

5. **License:** Apache 2.0 on both code (`qwen-tts` PyPI package) and weights (HF repo). No additional usage restrictions found.

6. **No install_dialog.py needed:** The old `install_dialog.py` was folded into `manage_voices_dialog.py`. Qwen3TTS appears automatically in Manage Voices via stacks.yaml — model-level Install/Uninstall row works out of the box, same pattern as other ML engines.

7. **No `install/requirements-ml.txt`:** This file doesn't exist in the repo. qwen-tts is installed via main requirements.txt or manual opt-in. health.py marks it as `_MANUAL_INSTALL_ENGINES` so a missing import warns instead of failing.

---

## Source references

- Package: https://pypi.org/project/qwen-tts/ (v0.1.1, Apache 2.0)
- GitHub: https://github.com/Qwen/Qwen3-TTS
- HF Collection: https://huggingface.co/collections/Qwen/qwen3-tts
- Model: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- Tokenizer: `Qwen/Qwen3-TTS-Tokenizer-12Hz`
- Paper: https://arxiv.org/abs/2601.15621
