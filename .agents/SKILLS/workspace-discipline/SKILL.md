---
name: workspace-discipline
description: Enforces strict boundary isolation when operating in workspaces containing multiple independent repositories. Prevents context leakage, cross-repo dependency assumptions, and unauthorized VCS/push mutations.
license: Apache-2.0
compatibility: Universal file-system access
metadata:
  author: AlienTech.Software
  version: "1.0"
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

### Secret & Credential Cordoning
- **Zero-Trust File Sweeps:** You are strictly prohibited from staging or committing files containing API keys, private tokens, local keychains, environment files (`.env`), or explicit developer credentials. 
- If a task requires configuring an engine API key (e.g., ElevenLabs or OpenAI for AlienVox), it must be hard-coded to look for native system environment variables or local hidden files specified in `.gitignore`. Never write raw credentials out to persistent workspace documentation or mock fixtures.