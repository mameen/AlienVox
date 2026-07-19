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
- `ui_ux_design`: defines the classic Win32/WPF functional aesthetic, layout hierarchy, menu bar, system tray behavior, and iconography for AlienVox surfaces.

## Implementation intent

Build concrete, runnable subsystems rather than speculative architecture. If a design decision is unclear, request clarification instead of guessing.

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
