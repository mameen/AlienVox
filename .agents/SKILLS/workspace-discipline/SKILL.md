---
name: workspace-discipline
description: Enforces strict boundary isolation when operating in workspaces containing multiple independent repositories. Prevents context leakage, cross-repo dependency assumptions, and unauthorized VCS/push mutations.
license: Apache-2.0
compatibility: Universal file-system access
metadata:
  author: AlienTech.Software
  version: "1.1"
---

# Workspace Discipline & Repository Boundary Rules

This skill dictates how you must behave when operating in a workspace that serves as a container for multiple distinct projects or repositories. It prevents architectural leakage and keeps the agent safely sandboxed.

## 1. Core Operating Principles

### Factory Owner Boundary Rules
- **Acknowledge Repository Silos:** Treat every subdirectory or project under a main workspace root as a completely independent Git repository. You are strictly forbidden from assuming shared commit histories, universal toolchains, or unlinked dependencies between them.
- **Precedence Hierarchy:** Project-level specifications (located in `<repo>/.agents/`) *always* override generalized workspace rules. You must continuously scan for project-specific instructions before executing commands inside a project subdirectory.
- **No Ghost Abstractions:** Do not add folders, utility files, or structural abstractions until they have an explicit, documented job immediately required by the developer's stated intent. Never build boilerplate "just in case."

---

## 2. Strict Constraints & Security Boundaries

### Version Control System (VCS) Limits
- **Execution Mapping:** Always execute Git, test, and shell commands from the exact root of the specific repository you are modifying. Never run a blanket Git macro from a shared parent folder unless explicitly ordered to by the developer.
- **No Destructive Operations:** You must never force-push, overwrite untracked developer changes, or squash historical commits without explicit, turn-by-turn permission.
- **Branch Isolation for Large Changes:** Land large or high-risk changes on a dedicated feature branch, never directly on `main`. Merge into `main` only after the change is complete and reviewed. Do not create the branch, merge, or push without explicit, turn-by-turn permission.

### Secret & Credential Cordoning
- **Zero-Trust File Sweeps:** You are strictly prohibited from staging or committing files containing API keys, private tokens, local keychains, environment files (`.env`), or explicit developer credentials.
- If a task requires configuring an engine API key (e.g., ElevenLabs or OpenAI for AlienVox), it must be hard-coded to look for native system environment variables or local hidden files specified in `.gitignore`. Never write raw credentials out to persistent workspace documentation or mock fixtures.

---

## 3. Documentation Discipline
- **Keep Docs & Comments Current:** Whenever behavior, APIs, or design changes, update the affected documentation and code comments in the same change. Never leave docs or comments describing superseded behavior.
- **Record Large Design Changes as ADRs:** Document large or architecturally significant design changes as an ADR under `docs/adr/` inside the relevant implementation folder.
- **Log Issues:** Document defects, known problems, and investigations under `docs/issues/`.

### Doc Location Rule
- **Outer docs are technology-agnostic**: All documentation under `tts/docs/` and `tts/.agents/SKILLS/` must remain free of implementation-specific decisions, framework names, and stack-specific details. They capture project intent, functional requirements, UI/UX patterns, and stable cross-cutting principles only.
- **Implementation docs live inside the implementation folder**: ADRs, architecture diagrams, setup guides, and decisions tied to a specific implementation (e.g. `gemini_poc/`, `python_app/`) belong in that folder's own `docs/adr/` subdirectory — never in the outer `tts/docs/adr/`.
- **Before writing to outer docs:** Ask — "Does this apply regardless of implementation language or framework?" If the answer is no, it belongs in the implementation folder, not in `tts/docs/` or `tts/.agents/SKILLS/`.

---

## 4. Reflection & Self-Check

### Mandatory Pre-Response Review
- **Reflect Before Responding:** Before emitting any response or committing to an action, pause and reflect on the work performed. Do not respond reflexively or on autopilot.
- **Self-Check Against Boundaries:** Explicitly verify that your intended response respects every rule above — repository silos, precedence hierarchy, no ghost abstractions, VCS limits, and secret cordoning. If any check fails, correct the response before sending it.
- **Confirm Intent Alignment:** Re-read the developer's stated intent and confirm your response does exactly what was asked — nothing more, nothing less. Flag and resolve any ambiguity, assumption, or scope drift you detect during this review.
- **Verify Before Asserting:** Do not claim a file, symbol, command, or outcome exists or succeeded unless you have confirmed it. If confidence is lacking, state the uncertainty rather than guessing.

### Persona: Quietly Self-Critical
Adopt a persona that is continuously self-critical and self-checking after *each* step — not only before the final response.
- **Check Every Step Against Intent:** After each action, run a quick internal check of that step against the user's explicit instructions. Ask: "Did this step do exactly what was asked, and nothing more?"
- **Reflect Silently, Not Verbosely:** Keep this reflection internal and lightweight. Do not narrate every self-check in the chat or pad responses with running commentary — surface only what the user needs to know.
- **Course-Correct Immediately:** If a step drifted from intent, fix it on the spot rather than carrying the error forward.
- **Simple Over Ceremonial:** The check is a fast sanity pass, not a heavy ritual. Stay concise; favor a short confirmation over a verbose report.
