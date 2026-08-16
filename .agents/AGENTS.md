# AlienVox AI Agent Guidance

This repository uses `.agents/` to control AI assistant behavior and ensure safe, repository-specific operations.

## Key rules

- Operate only inside `c:\dev\tts` and treat `python_app` as the active implementation area. `gemini_poc` is a retired Rust+Tauri POC — do not add new code there.
- Respect the existing skills in `.agents/SKILLS/` and load them only when relevant.
- Do not add broad workspace rules or cross-repo assumptions.
- Keep the prototype focused on MVP scope: tray support, minimal options, Windows local TTS, and one open-source ML/AI TTS provider.

## Relevant skills

- `workspace-discipline`: enforces repo boundary isolation, non-destructive VCS behavior, and reflect/self-check before responding.
- `highlevel_design`: enforces bridge patterns, platform isolation, anti-mocking philosophies, and the single standalone-binary production model.
- `dev-vs-prod`: defines the AlienVox dev/prod boundary, config locations, install assets, and packaging rules for source vs shipped state. **Key distinction:** `python_app/setup.py` is dev-only (venv bootstrap + weight download). The production installer lives in `python_app/install/`.
- `ui_ux_design`: defines the classic Win32/WPF functional aesthetic, layout hierarchy, menu bar, system tray behavior, and iconography for AlienVox surfaces.

## Read before you act

- **Always read the relevant source files first.** Never assume how something is implemented. Check `src/`, `stacks.yaml`, existing tests, and ADRs before proposing changes.
- **Understand the architecture before touching code.** The four-layer config system, engine registry, bridge pattern, and telemetry contract are all documented in `.agents/SKILLS/` and `docs/adr/`. Read them when relevant.
- **Never guess the user's intent from a vague prompt.** If the request is clear enough to act on — act. If not, ask one brief clarifying question (not five). The user can always follow up.

## Ask only what matters

- Clarifying questions must be **direct and under 2 sentences**. No preamble like "Just to clarify…" or "Could you confirm…".
- Example of good: "Voice dropdown — populate from stacks.yaml or engine.list_voices()?"
- Example of bad: "I wanted to just clarify, could you confirm whether the voice dropdown should be populated from the stacks.yaml file or from the engine's list_voices method? I want to make sure I understand correctly."
- **Never ask useless questions** about things already documented in ADRs, stacks.yaml, or existing code.

## Present options when the path is unclear

When there is no clear single answer, present 2–3 options with:

| Factor | Option A | Option B |
|--------|----------|----------|
| **Pros** | … | … |
| **Cons** | … | … |
| **Tokens** | ~Xk | ~Yk |
| **Complexity** | Low / Med / High | Low / Med / High |
| **Lines of code** | ~N | ~M |
| **Time** | ~Z min | ~W min |

Keep the table tight. The developer picks; you execute.

## UI architecture: MVC — wire new actions through the Controller

The Python app (`python_app/src/`) is MVC: `src/model/` (`AppState`, a `QObject` with `Signal`s —
plus `engines/`), `src/control/` (`AppController` — the only thing that mutates `AppState`), and
`src/view/` (`MainWindow`, `AlienVoxTray` — reactive Views that read `AppState` and call
`AppController`). Full rules and the reference pattern live in
`.agents/SKILLS/highlevel_design/SKILL.md` §7 and `python_app/docs/adr/adr-004-mvc-architecture.md`.

When a task adds or changes a user-facing action that touches application state:

- **Think "what AppController method does this need?" before touching any View file.** A new
  toolbar button, menu item, or setting is a new (or reused) `AppController` method — never a
  callback threaded through `MainWindow.__init__`/`AlienVoxTray.__init__`, and never a View
  mutating `AppState` directly.
- If the action needs new state, add it to `AppState` with a setter + `Signal`, not as a variable
  living in a View or in `main.py`.
- Wire side effects (engine reload, persistence) by connecting `AppController.__init__` to
  `AppState`'s own signal — so the side effect fires no matter which caller triggered the state
  change, not just the one you're adding right now.
- Every View that displays the changed state must subscribe to the new signal and update its
  widgets from that slot (with `blockSignals()` guarding against feedback loops) — a View updating
  only in response to its *own* widget's callback is exactly the bug pattern this architecture
  replaced (recurring model/voice desync, fixed in `adr-004-mvc-architecture.md`).
- If you're unsure whether an action belongs in `AppController` vs. staying a View-local, one-shot
  concern (e.g. opening a modal dialog), see SKILL.md §7.4 — one-shot dialogs are explicitly
  exempt from the `AppState` signal contract.

## VCS safety

- Create a private branch for any non-trivial work. Be ready to merge and push to `main` after user approval.
- Never force-push or delete shared branches.

## Do the right thing — never procrastinate on hard work

- **Recommend the correct path, not the easy one.** If two options exist and one is honest-but-hard while the other is quick-but-wrong, recommend the honest one and say so plainly. Do not hedge toward the easy option to avoid effort.
- **Do not defer real work by stubbing, hiding, or renaming a problem.** Hiding a broken model from a dropdown is not a fix; writing the missing adapter is. Stubs are only acceptable when explicitly scoped and time-boxed by the developer.
- **No "let's revisit this later" without a written follow-up.** If a task is genuinely deferred, record it under `docs/issues/` as a concrete todo with the reason.
- **When a task is hard, do it anyway.** Difficulty is not a reason to substitute a lighter task. Break it into steps, size each step, and start.

## Estimation is mandatory

Before proposing any non-trivial change (new subsystem, adapter, refactor spanning multiple files, dependency addition), include an estimate in the recommendation:

- **Tokens**: rough output-token budget for the change (e.g. `~4k tokens` for a 150-line worker script + wiring). Order-of-magnitude is fine.
- **Time**: wall-clock estimate for the developer to review and land the change end-to-end, including build + smoke test (e.g. `~45 min`, `~2 h`, `~half a day`). Be honest — pad for dependency install or first-run model downloads when relevant.
- **Risk / unknowns**: one line naming the biggest unknown (e.g. "VibeVoice audio decoder API stability on Windows Python 3.11").

Estimates apply to both options in a "pick A vs B" recommendation, so the developer sees the trade-off in the same units.

## Skill vs MCP server: real per-turn token cost

When recommending between `.agents/SKILLS/alien_vox` (Claude Code Skill) and `python_mcp_server`
(MCP server) for a task, the two are not interchangeable on context-window cost — measured for
real with `tiktoken`'s `cl100k_base` encoding, not estimated:

| Surface | What loads every turn | Tokens | Chars | Tokens/1K chars |
|---|---|---:|---:|---:|
| `alien_vox` Skill | `SKILL.md` frontmatter (`name` + `description`) only, until triggered | 95 | 398 | ~239 |
| `python_mcp_server` | Full `list_tools()`/`list_resources()`/`list_prompts()` schema (7 tools, 2 resources, 1 prompt) | 953 | 4,052 | ~235 |

The tokens-per-1K-chars rate is nearly identical (~235–239) — the gap isn't tokenizer efficiency,
it's *what's forced into context on every single turn*. MCP's tool discovery sends the full schema
list on every turn of a session that has the server connected, whether or not AlienVox is used that
turn — **~10x** the Skill's steady-state footprint. The Skill only pays a larger one-time cost
(~1,688 tokens, the full `SKILL.md` body) once it's actually triggered by a matching request.

**Default to the Skill** for any Claude Code session unless the task specifically needs MCP's
protocol-level exposure (e.g. a non-Claude-Code MCP host, or programmatic tool/resource/prompt
discovery). Re-measure if either surface's tool count or `SKILL.md` grows meaningfully — these
numbers are a real snapshot, not a permanent constant.

## Canonical Sample Phrase

All ML engines must use the same canonical sample phrase for voice samples and performance tests. This ensures consistent, comparable results across all engines.

**Source:** `python_app/src/control/app_controller.py` — `SAMPLE_TEXT`

```
Welcome to AlienVox. This is a performance test of your TTS engine. If you can hear this, your system is working correctly.
```

**Rules:**
- All offline voice samples in `install/assets/audio/ml/<model>/` must use this exact phrase.
- All performance tests (`tests/test_perf.py`) import this as `WELCOME_PHRASE`.
- Never use arbitrary text (like "quick brown fox") for voice samples — always use the canonical phrase.
- When generating new voice samples, reference `app_controller.py`'s `SAMPLE_TEXT`, not a hardcoded string in your generation script.
