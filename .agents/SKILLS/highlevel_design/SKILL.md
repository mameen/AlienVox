---
name: cross-platform-development
description: Guidelines for implementing cross-platform desktop modules using the Bridge pattern. Enforces strict OS isolation, anti-mocking test state philosophies, and absolute adherence to intent without shortcuts.
license: Apache-2.0
compatibility: Cross-platform environment (Windows 11 / macOS 14+)
metadata:
  author: AlienTech.Software
  version: "2.1"
---

# Cross-Platform Architecture & Development Guidelines

This skill codifies the architectural, structural, and testing standards required to build low-latency, deterministic, cross-platform components for AlienTech.Software projects (such as AlienVox). It is **technology-agnostic**; implementation-specific details (language, framework, crates, packages) live in each implementation's own `docs/adr/` folder.

## 1. Core Principles

### Factory Owner, Not Coder
- **Anchor to Intent:** Your goal is to express and fulfill the developer's exact stated intent. If instructions or requirements are ambiguous, you must stop and ask; never silently infer context.
- **Zero Shortcuts:** You are strictly forbidden from taking shortcuts, collapsing multiple complex tasks into single compromises, or skipping steps because an implementation is complex. Keeping an application simple means executing clean, unbloated designs—it *never* means delivering an incomplete, cut-corner, or incorrect feature.
- **Surface Assumptions:** Explicitly state what you are about to assume and wait for user confirmation before executing any code changes.

### Anti-Mocking Testing Philosophy
- **Real Code Execution:** Mocking dependencies is strongly discouraged. Unit tests and functional integration pipelines must execute actual, deterministic code branches against real buffers wherever possible.
- **Concrete Test Data:** Provide explicit, real-world mock data files, clipboard structures, or memory state vectors to test genuine logic rather than simulating structural responses through arbitrary mock interfaces.

---

## 2. Structural Patterns: The Bridge & Suffix Isolation

Every system-level subsystem must be separated into a platform-agnostic abstract contract layer and isolated, platform-specific concrete implementations.

### 2.1 File Suffix Mapping Rules
For standalone or lightweight structural integrations, use strict suffix tracking:
- `*._core.*` / `*._base.*` — Contains the common interface/protocol definition. Absolutely no platform imports allowed.
- `*_win.*` — Isolated platform execution for Windows 11 (Win32, COM, UI Automation APIs).
- `*_mac.*` — Isolated platform execution for macOS 14+ (Cocoa, AppKit, AVFoundation APIs).
- `*_lnx.*` — Isolated platform execution for Linux kernels (X11, Wayland, DBus).

### 2.2 Subsystem Directory Isolation
For intricate multi-file pipelines (e.g., local OCR engines or native accessibility tree scrapers), separate modules inside platform-specific child directories managed by a top-level dispatcher:

```text
engines/<subsystem-name>/
├── __init__ / mod       # Directs dispatch dynamically based on platform
├── base                 # Houses the abstract protocol or shared definitions
├── win/                 # Fully cordoned Windows logic paths
│   └── text_grabber
└── mac/                 # Fully cordoned macOS logic paths
    └── text_grabber
```

---

## 3. Single-Application Runtime — Non-Negotiable

AlienVox **MUST** ship as one application: a single process, a single executable, no external runtime dependencies at inference time. There is no separate backend process, sidecar server, or second runtime interpreter. Any design that splits the runtime into multiple applications violates this rule.

The implementation language (chosen per each implementation's ADR-001) is the runtime that calls all TTS models — either natively in-process or through OS APIs. No subprocess calls to an external interpreter at inference time are permitted; that pattern is hidden-backend architecture in disguise.

---

## 4. Model Integration Paths

### 4.1 Path A — Cloud / Remote Models
- Hosted TTS providers (e.g., OpenAI, ElevenLabs, Azure) are HTTPS REST/streaming APIs.
- Call them directly from within the app process using an async HTTP client, consuming streamed audio chunks to preserve low latency.
- API keys resolve from native system environment variables or `.gitignore`-d local files — never hard-coded or committed.

### 4.2 Path B — Local / Open-Source ML TTS Models
Open-source neural TTS models must be integrated **in-process** — no subprocess calls to an external interpreter at runtime.
- **ONNX Runtime** — export the model to ONNX and run inference in-process (e.g., Piper-style TTS). Preferred default for cross-language portability.
- **Native ML framework** — use the language-native ML library to load and run the model directly (e.g., PyTorch in Python).
- **Bundled native inference binary** — a compiled engine driven from the app process as a linked library, not a subprocess.

### 4.3 Native OS TTS Fallback
Local, zero-dependency speech via the platform's built-in engine is the fastest fallback and must always be available:
- **Windows:** SAPI5 / WinRT via COM or the platform's native binding.
- **macOS:** AVFoundation / `NSSpeechSynthesizer` via the `mac` platform path.

### 4.4 Constraint Summary
- "Call other TTS models from inside the app" means in-process native inference — never a subprocess spawning an external interpreter.
- The model-integration layer follows the Bridge & suffix isolation rules of Section 2 like any other subsystem.

### 4.5 Adding a New Local ML Engine — Checklist (python_app)

A new engine touches the **same fixed set of surfaces** every time — treat this as a checklist,
not a menu; skipping one leaves a real gap (a UI entry with no engine behind it, an untested code
path, weights that install to the wrong directory). Reference implementation: VibeVoice-Realtime-0.5B
(`src/engines/vibevoice_engine.py`, `docs/issues/todo_006.md` for the research/decision trail behind it).

**0. Research before building — a model card is not a green light.** Before writing the engine,
actually install the package, download real weights, and run real inference in a **throwaway venv
outside the repo** (never into the dev venv or `.models/` speculatively). Verify, don't assume:
license terms from the actual `LICENSE` file text (not just a badge or a README blurb), real
install complexity (PyPI vs. git-only, hidden heavy dependencies), and real performance (measure
wall-clock latency / RTF — a "Realtime" name or a marketing claim is not evidence). Write the
findings into a `docs/issues/todo_NNN.md` before touching any application code. If the license
carries a non-binding "not recommended for X" disclaimer, surface it explicitly as a business
decision — don't silently adopt or silently ignore it.

**1. Engine module** — `src/engines/<name>_engine.py`, subclassing `TtsEngine` (`engines/base.py`).
Follow the existing shape: class-level model singleton behind a `threading.Lock()`, a daemon thread
per `speak()` call, `synthesize()` returning `(float32 array, sample_rate)` for export/perf-test
support, volume scaling applied post-synthesis, `stop()`/`wait_until_done()` using
`threading.Event()`s. Weights and any per-voice extra assets (presets, reference clips) load from
`models_root() / "ml" / "<name>"` (`src/config.py`) — **never** the bare global HF cache via a plain
`from_pretrained(repo_id)` — every other model's weights live under `.models/`, and a new engine that
doesn't follow suit breaks the "one place to look" invariant `python run.py health` and the install
dialog both depend on.

**2. `stacks.yaml`** — new model entry under the `ml` stack: `id`, `name`, `weights_subpath`,
`auto_download`, `voices` (id + label pairs), `controls` (mark unsupported controls
`applies: false` — see §5.4's UI Hint Schema). This one entry is what makes the model appear in
the Manage Voices dialog and the main window's voice dropdown — **no UI code changes are needed**
for those two surfaces; they're both driven entirely by this catalog + `engines/registry.py`.

**3. `src/control/app_controller.py`** — one line in `_ML_ENGINES`: `"<model_id>": ("<name>_engine", "<ClassName>")`.

**4. `setup.py`** — add to `_download_auto`'s HF-repo map for weight download, plus a
`_provision_<name>_voices()` step (mirror `_provision_f5tts_reference_voice`/
`_provision_chatterbox_reference_voices`) if the model needs extra per-voice assets beyond the base
HF snapshot.

**5. `install_dialog.py`** — a `_build_<name>_ui`/`_download_<name>` branch alongside the existing
Kokoro/Piper ones, wired into `_build_ui`'s dispatch and `_on_download`'s task selection.

**6. `about.py`'s Tech Stack blurb** — add or correct the one-line mention. If step 0 surfaced a
real caveat (license disclaimer, measured non-real-time performance, GPU requirement), state it
here plainly — don't leave an aspirational-sounding blurb standing once real numbers exist.

**7. `3P.md`** — new entry in §2 (ML Models) with license (code + weights separately verified),
source URL, and an explicit callout of any responsible-use disclaimer found in step 0.

**8. `install/requirements-*.txt`** — if the package isn't a clean `pip install <name>>=X` from
PyPI (git-only, or pulls unrelated heavy dependencies), document it as **manual/opt-in only** — a
comment with the exact install command, not an auto-installed line — same treatment as Dia and
VibeVoice. Don't let one engine's dependency bloat force itself onto every ML user.

**9. Tests — real, not mocked (see `testing` SKILL, this is not optional):**
   - `tests/fixtures/stacks.yaml` — mirror the new `stacks.yaml` entry (a *separate* fixture
     catalog from the bundled one — perf tooling and `available_stacks()` tests read this one, not
     the real `stacks.yaml`).
   - `tests/conftest.py`'s `_ALL_ML_MODELS` — add the new `ml/<name>` weights subpath so
     `requires_weights()` gating covers it.
   - `tests/test_<name>.py` — mirror `test_outetts.py`'s shape: pure-logic voice-roster tests (no
     gating needed), then `@requires_weights("ml/<name>")`-gated real-synthesis tests covering: a
     default voice, **at least one additional distinct voice** (e.g. a female preset when the
     roster has one — don't only ever test voice #1), volume scaling, invalid-voice fallback, and
     `speak()` → `play_audio()` wiring (with `play_audio` itself stubbed — the OS/hardware edge is
     the one acceptable mock boundary per the `testing` SKILL, the buffer feeding it must be real).
   - `tests/test_perf.py`'s `_load_ml_engine()` — add the new model's dispatch branch so
     `python run.py perf` (full sweep) and `python run.py perf --stack ml --model <name> --voice
     <id>` (single-case — see `run.py`'s `cmd_perf` docstring) both pick it up.

**10. `src/health.py`** — add to `_ML_ENGINE_IMPORTS`; if the package is manual/opt-in (step 8),
add its `id` to `_MANUAL_INSTALL_ENGINES` so a missing import warns instead of failing
`python run.py health`. If the model needs extra per-voice assets beyond the base weights (step
4's provisioning step), add a dedicated presence check (see `_check_vibevoice_preset_voices` for
the pattern) — the generic "does the weights directory have *any* file in it" check will not catch
a partial download (weights present, only 2 of 6 voice presets fetched).

A new engine is not done until **every** step above has landed — a "Download" button with no engine
behind it, or an engine with no `stacks.yaml` entry, is a dead end for the next person (or agent)
who finds it.

---

## 5. Configuration — One-Way Data Flow

Every configurable setting in AlienVox is owned by a YAML descriptor on disk. The
engine layer, the UI, and telemetry all **read** from the merged config; user input
**writes** back to the config file and the app reloads. No code path mutates engine
state, UI widgets, or persisted values out-of-band. This keeps state single-sourced,
diffable, and testable without a running app.

### 5.1 Read / Write Directions

- **Read (fan-out)**: YAML → engine construction, YAML → UI control rendering, YAML → telemetry stack configuration.
- **Write (single sink)**: user input → YAML file → reload → fan-out again.
- The UI **must not** hard-code model-specific fields (voice lists, rate/pitch ranges, install manifests). If a knob isn't declared in YAML, it isn't rendered. Adding a new model means dropping a folder with `model.yaml` — no application code edits.
- The engine **must not** cache setting values past a reload. Every `speak` reads the effective config for the current stack/model/voice.

### 5.2 Four-Layer Config Hierarchy

Later layers override earlier ones. The resolver merges bottom-up and hands the
flattened view to both the engine and the UI.

| # | Layer | Location | Purpose |
| :--- | :--- | :--- | :--- |
| 1 | Built-in defaults | Compiled into the engine | Baseline values so a missing YAML never crashes the app. |
| 2 | Stack config | `.models/<stack>/stack.yaml`, `.apis/<provider>/provider.yaml` | Stack- or provider-wide settings (default TTL, models root, API base URL, auth env-var name). |
| 3 | Model / voice config | `.models/<stack>/<model>/model.yaml` | Per-model knobs, voice roster, install manifest, UI hints (control ranges, labels, which sliders apply). |
| 4 | User overrides | Platform app-data dir (e.g. `%LOCALAPPDATA%\<identifier>\user.yaml` on Windows) | Last-picked engine/model/voice, slider values, hotkey binding — the persisted UI state. |

### 5.3 Concrete Paths

- Stacks live under `.models/<stack>/`.
- Cloud providers live under `.apis/<provider>/` alongside `.models`.
- All paths resolve through a unified path-resolution utility in the implementation (see that implementation's ADR for specifics). The config resolver reuses that search order — it does **not** invent its own path scheme.
- Secrets referenced by `provider.yaml` (API keys) resolve from OS environment variables named in the YAML; the key value is never written into any YAML on disk (per `workspace-discipline` §2 secret cordoning).

### 5.4 UI Hint Schema (informative)

Model YAML declares what the UI should render, so the frontend is a generic renderer:

```yaml
# .models/ml/kokoro/model.yaml (illustrative)
id: kokoro
name: Kokoro-82M
voices:
  - { id: af_heart, label: "American F · Heart" }
  - { id: bm_george, label: "British M · George" }
controls:
  rate:   { min: -10, max: 10, default: 0, applies: true }
  pitch:  { applies: false }     # Kokoro ignores pitch — hide the slider
  volume: { min: 0, max: 100, default: 100, applies: true }
  ttl_seconds: { min: 0, max: 300, default: 30, applies: true }
```

An engine that doesn't map a field marks it `applies: false`; the UI reclaims the
space (aligns with `ui_ux_design` §2.2). This replaces ad-hoc per-model branches in
the engine and the frontend.

### 5.5 Consequences

- **Adding a stack, provider, or model is data-only** in the steady state.
- **Persistence is trivial**: writing `user.yaml` is the only mutation site.
- **Diffing is straightforward**: `git diff` on the config folder shows exactly what changed between runs.
- **Testing is decoupled**: engine and renderer tests take a YAML fixture instead of mocking IPC.

---

## 7. Python App — UI Architecture Pattern (MVC)

### 7.1 Current Pattern: MVC (AppState + AppController)

The Python app (`python_app/src/`) is **MVC**, split into three top-level packages:

- `src/model/` — `app_state.py` (`AppState`, a `QObject` holding all active stack/model/voice/
  params state, `Signal`-backed) plus the `engines/` hierarchy and `audio_player.py` (kept at
  `src/` root — treat them as Model-layer even though the directory isn't literally under
  `src/model/`).
- `src/control/` — `app_controller.py` (`AppController`, the **only** thing that mutates
  `AppState`), plus `hotkey.py`, `capture.py`, `telemetry.py`, `audio_exporter.py`.
- `src/view/` — `main_window.py` (`MainWindow`), `tray.py` (`AlienVoxTray`), `about.py`,
  `export_dialog.py`, `install_dialog.py`. Views read `AppState` and call `AppController`; they
  never mutate `AppState` directly and never touch engine objects themselves.

See `adr-004-mvc-architecture.md` for the full decision record and the bug history that motivated
this split (recurring model/voice desync — a View showing state that didn't match what was
actually active, because there was no single object both sides read from).

**Key invariant**: Views hold **no mutable application state** of their own beyond widget
contents, and those contents are always driven by an `AppState` signal handler — never a
constructor snapshot, never a separate "push" method called ad hoc from outside. Every user action
in a View calls an `AppController` method; `AppController` mutates `AppState` through its setters;
`AppState` emits a signal; every View's slot for that signal updates itself. One-directional,
traceable:

```
View event -> AppController method -> AppState mutation -> Signal -> every View's slot updates
```

### 7.2 Adding a new user-facing action — the required steps

When a new action needs to change application state (not a one-shot dialog like Export/About —
see §7.4 for those), do **all** of the following. Skipping any step reintroduces the exact bug
class this architecture exists to prevent:

1. **If the state is new**, add a field + setter + `Signal` to `AppState` (`src/model/app_state.py`).
   The setter must no-op when the value is unchanged and must be the *only* way that field is
   written — no direct attribute assignment from outside `AppState`.
2. **Add a method to `AppController`** (`src/control/app_controller.py`) that calls the `AppState`
   setter(s). This is the command surface — every state-changing action is a named method here,
   not a callback threaded through a View constructor.
3. **If the change should trigger a side effect** (engine reload, persistence), wire it in
   `AppController.__init__` by connecting to `AppState`'s own signal — not by remembering to call
   the side effect inline in step 2's method. This is what makes side effects automatic regardless
   of which code path triggered the state change (a View's combo, Load Settings, the tray menu).
4. **In each View that displays this state**, connect a slot to the new signal in `__init__` and
   update the relevant widget(s) there — with `combo.blockSignals(True)` bracketing the update if
   the widget also has a user-input signal that would otherwise re-fire and call back into the
   Controller. See `_on_state_model_changed` in `main_window.py` for the reference pattern.
5. **Call the `AppController` method from the View's own widget signal handler** for the
   interactive path (e.g. a `QComboBox.currentIndexChanged` handler calling
   `self._controller.select_voice(vid)`).

A new action is **not done** until both directions work: triggering it from the UI, and having
every View reflect a change that originated somewhere else (test this explicitly — see
`tests/test_main_window.py::test_model_combo_change_updates_state_and_reflects_in_voice_combo` for
the pattern).

### 7.3 Reactive-update sharp edge: signal feedback loops

A View's widget often has two signal directions: the widget's own Qt signal (fires on user
interaction) and an `AppState` signal that this View also updates the widget from (fires
regardless of origin). Without guarding, a state-driven update (`combo.setCurrentIndex(...)`)
re-fires the widget's own signal, which calls back into `AppController`, which may re-mutate
`AppState` — usually harmless (the setter no-ops on an unchanged value) but wasteful and, in cases
involving `.clear()` + repeated `.addItem()`, can fire spurious intermediate signals. Always
bracket a reactive widget update with `blockSignals(True)` / `blockSignals(False)`:

```python
def _on_state_voice_changed(self, voice_id: str) -> None:
    for combo, sid in self._voice_combos:
        if sid != self._state.active_stack:
            continue
        combo.blockSignals(True)
        idx = combo.findData(voice_id)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
```

### 7.4 One-shot dialogs are explicitly out of scope

Transient, one-shot modal operations (`AboutDialog`, `ExportDialog`, `InstallDialog`) are
constructed directly by the View when needed, using a snapshot of current state
(`self._controller.build_current_speak_params()`, `self._state.voice`, `self._controller.engine`).
They are not part of the `AppState`/signal contract — there's no ongoing state to keep in sync
once the dialog is open, so the extra indirection isn't worth it.

---

## 6. Architecture Decision Records (ADRs)

All significant, long-lived architecture decisions for an AlienVox implementation are recorded as ADRs in that **implementation's** `docs/adr/` folder (e.g. `gemini_poc/docs/adr/`, `python_app/docs/adr/`). Before proposing or implementing a large design change, **consult the existing ADRs** for prior decisions and constraints, and **record new large design decisions** as a new `adr-00N-<slug>.md` following the established format (Status, Date, Context, Decision, Consequences, Related Decisions). Keep ADRs cross-linked.

Outer project ADRs (under `tts/docs/adr/`) are reserved for project-wide, technology-agnostic decisions only. Implementation-specific ADRs (stack selection, deployment model, path resolution, engine architecture) belong inside the implementation folder per the `workspace-discipline` Doc Location Rule.

---

## 8. Dev vs Prod Identity Separation — Non-Negotiable

AlienVox running from source (`python run.py app`, dev) and a real installed/frozen copy (`prod`)
are **separate identities in every OS-level and filesystem-level way**, always, without exception.
Running both simultaneously on the same developer machine must work correctly, with each enforcing
its own single-instance rule independently — one must never falsely block or contaminate the other.

Concretely, gated on `getattr(sys, "frozen", False)`:

| Surface | Dev | Prod (frozen) |
| :--- | :--- | :--- |
| Model weights (`config.py`'s `models_root()`) | `<repo>/python_app/.models`, **always**, unconditionally — never checks whether `%LOCALAPPDATA%` has anything | `%LOCALAPPDATA%\com.alientech.alienvox\.models`, always |
| `stacks.yaml` / `user.yaml` | Next to `setup.py` (repo-relative) | Next to the installed executable |
| Telemetry sink (`telemetry.py`) | Repo-local `.logs/*.jsonl` **only** | `%LOCALAPPDATA%\...\telemetry\*.jsonl` **only** |
| Log sink (`logger.py`) | Repo-local `.logs/*.log` **only** | Both repo-local (best-effort, usually a no-op) **and** `%LOCALAPPDATA%\...\logs\*.log` |
| Single-instance mutex (`single_instance.py`) | `Global\AlienVox_SingleInstance_Dev` | `Global\AlienVox_SingleInstance` |
| Legacy `user.yaml` AppData migration read | Never runs | One-time read of the legacy AppData path, if the new location is still empty |

**Why this is a hard rule, not a preference:** it was violated in two different, real, previously
undetected ways (`docs/issues/issue_002.md`), only surfaced while chasing unrelated test failures:

1. `models_root()` used to prefer `%LOCALAPPDATA%\...\.models` over the repo-local dev path
   *whenever that AppData directory happened to already exist* — which it did, on a machine that
   had run an installed/frozen build at some earlier point. Every dev-mode weight lookup silently
   started resolving to the (differently-populated) AppData directory instead, with real engines
   reporting "weights missing" for weights that were sitting right there in the repo folder.
2. `telemetry.py` and `logger.py` wrote to **both** the repo-local sink and the AppData sink
   **unconditionally, regardless of `sys.frozen`** — meaning every single dev run, always, was
   silently mixing its telemetry/logs into the same folder a real installed copy uses.

**The fix pattern, and the one to follow for any new AppData-touching code:** never decide "which
location" based on "does the other location happen to exist" — decide based on `sys.frozen` alone,
every time, with no existence-based fallback preference in either direction. A location existing or
not existing is `models_root()`-internal, empty-directory-creation plumbing, never a routing signal
across the dev/prod boundary.
