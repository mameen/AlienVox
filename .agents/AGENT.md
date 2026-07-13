# AlienVox AI Agent Guidance

This repository uses `.agents/` to control AI assistant behavior and ensure safe, repository-specific operations.

## Key rules

- Operate only inside `c:\dev\tts` and treat `gemini_poc` as the active implementation area.
- Respect the existing skills in `.agents/SKILLS/` and load them only when relevant.
- Do not add broad workspace rules or cross-repo assumptions.
- Keep the prototype focused on MVP scope: tray support, minimal options, Windows local TTS, and one open-source ML/AI TTS provider.

## Relevant skills

- `workspace-discipline`: enforces repo boundary isolation and non-destructive behavior.
- `highlevel_design`: enforces bridge patterns, platform isolation, and anti-mocking philosophies.

## Implementation intent

Build concrete, runnable subsystems rather than speculative architecture. If a design decision is unclear, request clarification instead of guessing.
