# TODO #007: Installation assets, default config, and dev/prod split

**Status:** Open
**Updated:** 2026-07-26
**Scope:** `python_app/setup.py`, `python_app/run.py`, `python_app/stacks.yaml`, `python_app/src/config.py`, `python_app/src/model/app_state.py`, `python_app/src/control/app_controller.py`, `python_app/src/view/manage_voices_dialog.py`, `python_app/src/view/main_window.py`, `python_app/src/view/tray.py`, installer packaging under `python_app/install/`, and the new skill at `.agents/SKILLS/dev-vs-prod/`.

---

## Goal

Make installation and environment behavior explicit and one-way:

- ship a default supported-voice catalog with the app
- install preview audio as assets, not as model weights
- keep user config separate from bundled defaults
- keep dev-mode behavior flexible, but keep prod behavior crisp and deterministic
- let the UI show offline samples even when a model is not installed

This todo is intentionally detailed so a smaller model can implement it step by step without guessing.

---

## Why this matters

The current repo already mixes several responsibilities:

- `stacks.yaml` is the supported catalog
- `.models/` is the installed-weights store
- `.generated/` is a benchmark/output scratch area
- installer scripts also need to provision model-specific reference assets

That works today, but it is too easy for a future change to:

- conflate bundled defaults with user-writable state
- delete preview assets during uninstall
- put config in the wrong place for dev vs prod
- make the app guess where a voice definition lives

This todo exists to prevent that drift.

---

## Target design

### Source of truth

- Keep `stacks.yaml` as the authoritative supported catalog for stacks, models, and voices.
- Copy the default catalog into the user install location during installation.
- Load the copied user-local catalog at runtime.

### Preview assets

- Store voice preview MP3s under the installer asset tree, not under `.generated/`.
- Keep preview assets independent from installed model weights.
- Do not delete preview assets when uninstalling a model or voice.

### Model installation

- Treat model weights as optional runtime downloads.
- Treat "basic install" as app + config + preview assets only.
- Treat "advanced install" as opt-in model download during installation.

### UI behavior

- If a voice is installed, show a live play action.
- If a voice is not installed but the preview sample exists, show an offline play action.
- If both exist, show both actions.
- Do not hide an unsupported voice just because its weights are missing.

### Dev vs prod

- Dev mode may use repo-local defaults and more logging.
- Prod mode must use the shipped catalog and installed assets.
- Do not use the registry as the primary state store for cross-platform behavior.

---

## Files to inspect first

Read these before coding:

- [`python_app/setup.py`](C:\dev\personal\.repos\tts2\python_app\setup.py)
- [`python_app/run.py`](C:\dev\personal\.repos\tts2\python_app\run.py)
- [`python_app/stacks.yaml`](C:\dev\personal\.repos\tts2\python_app\stacks.yaml)
- [`python_app/src/config.py`](C:\dev\personal\.repos\tts2\python_app\src\config.py)
- [`python_app/src/model/app_state.py`](C:\dev\personal\.repos\tts2\python_app\src\model\app_state.py)
- [`python_app/src/control/app_controller.py`](C:\dev\personal\.repos\tts2\python_app\src\control\app_controller.py)
- [`python_app/src/view/manage_voices_dialog.py`](C:\dev\personal\.repos\tts2\python_app\src\view\manage_voices_dialog.py)
- [`python_app/src/view/main_window.py`](C:\dev\personal\.repos\tts2\python_app\src\view\main_window.py)
- [`python_app/src/view/tray.py`](C:\dev\personal\.repos\tts2\python_app\src\view\tray.py)
- [`python_app/install/README.md`](C:\dev\personal\.repos\tts2\python_app\install\README.md)
- [`python_app/docs/issues/todo_006.md`](C:\dev\personal\.repos\tts2\python_app\docs\issues\todo_006.md)
- [`.agents/SKILLS/dev-vs-prod/SKILL.md`](C:\dev\personal\.repos\tts2\.agents\SKILLS\dev-vs-prod\SKILL.md)
- [`.agents/SKILLS/dev-vs-prod/references/dev_prod_reference.md`](C:\dev\personal\.repos\tts2\.agents\SKILLS\dev-vs-prod\references\dev_prod_reference.md)

---

## Proposed implementation steps

### 1. Normalize the config model

- Keep the supported catalog in one canonical bundled config.
- Make the installer copy that config into the user install location.
- Ensure runtime reads the user-local copy, not a hand-rolled duplicate.

Acceptance:

- The app loads the same catalog structure in dev and prod.
- A user-local config file exists after installation.
- The bundled config remains read-only at runtime.

### 2. Add install assets for preview audio

- Move the MP3 preview set into `python_app/install/assets/audio/` or another installer-owned asset folder.
- Keep the asset tree source-controlled if the files are intentionally shipped.
- Preserve a manifest that maps `stack/model/voice` to a preview asset path.

Acceptance:

- Preview assets are present in the installer tree.
- Uninstalling model weights does not remove preview assets.
- Offline preview lookup does not depend on the model being installed.

### 3. Add a build/setup generation mode

- Add a `--generate-audio` or similarly named setup flag.
- Have it regenerate the preview MP3 set from the canonical voice catalog.
- Make it idempotent so repeated runs do not create duplicates or stale paths.

Acceptance:

- A setup command can regenerate the preview assets from the current catalog.
- The generated format is MP3 by default for shipped previews.
- A WAV fallback may still exist for debugging, but the shipped asset path should be MP3.

### 4. Wire basic vs advanced install

- Basic install:
  - app
  - user-local config copy
  - preview assets
  - no model downloads
- Advanced install:
  - warning dialog about network time, partial failures, and optional later install
  - optional model download step
  - optional per-voice/model selection

Acceptance:

- Basic install stays fast and low-risk.
- Advanced install clearly warns about download time and failures.
- User can finish basic install without downloading large model weights.

### 5. Update the voice UI

- Add offline sample playback in `ManageVoicesDialog`.
- Add a live-play button when model weights are installed.
- Keep the sample button available even when weights are missing.
- Make uninstall preserve samples.

Acceptance:

- A voice can be previewed before install.
- Installed voices can be previewed live.
- Uninstalling a model/voice does not remove the shipped sample.

### 6. Document dev/prod boundaries

- Add a source-of-truth reference for config paths, user config paths, and install asset locations.
- Document what belongs in source control and what belongs in user data.
- Document that registry-based storage is not the default cross-platform answer.

Acceptance:

- The new skill explains the file-role split clearly enough for a smaller model to follow.
- Future install-related tasks can reuse the reference without rediscovering the whole architecture.

---

## Suggested file layout

- `python_app/install/assets/audio/` for shipped preview MP3s
- `python_app/install/assets/voice-manifest.yaml` for preview mappings if needed
- `python_app/install/generated/` or a build scratch area for temporary regeneration outputs
- `python_app/docs/issues/todo_007_installation_and_dev_prod.md` for the implementation plan
- `.agents/SKILLS/dev-vs-prod/` for the reusable guidance

---

## Risks and unknowns

- Need to confirm the installer packaging step picks up the new assets folder.
- Need to confirm the user-local config copy path for both dev and installed builds.
- Need to make sure the UI can distinguish live preview from offline sample preview without confusing the user.
- Need to keep uninstall from deleting preview audio.
- Need to avoid putting large binary assets in the wrong place if a later packaging step prefers a different folder.

---

## Done means

- The installer has a clear basic/advanced split.
- Preview assets are shipped in an installer-owned location.
- The runtime catalog comes from one config source.
- Dev/prod path rules are documented in the new skill.
- The voice UI can offer both live and offline preview modes.
