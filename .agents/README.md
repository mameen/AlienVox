# AI Agent Configuration — Convention Guide

`.agents/` is the **source of truth** for all AI agent configuration in a repo. Everything is committed to Git here; other tool-specific locations are symlinks pointing back to this directory.

## Philosophy

- One place to edit, many tools supported via symlinks.
- Each repo gets its own `.agents/` — nothing is shared across repos automatically.
- Only set this up when a repo actually needs it, not preemptively.

## How I Work With AI Assistants

### Factory Owner, Not Coder

The shift from writing code to working with AI agents is a shift in role: from **implementer** to **factory owner**. The developer's job is to express *intent* — what must be discovered, validated, ranked, or produced — and let deterministic tools (scripts, validators, tests) handle any pass/fail verification. LLM guessing is never a substitute for a real check.

Practically, this means an agent must:
- **Anchor to the developer's stated intent** — if the intent is ambiguous, ask; don't infer silently.
- **Never take shortcuts** without explicit approval (e.g., skipping a validation step, collapsing two tasks into one, assuming a default).
- **Surface assumptions before acting on them.** State what you're about to assume and wait for a go-ahead.

### Progressive Context Disclosure

Prefer a **single agent that loads context on demand** over a fixed multi-agent graph (concierge → researcher → synthesizer, etc.). Hard-wired topologies cause context rot: each hand-off re-reads overlapping material and produces summaries of summaries — the signal degrades.

Instead, skills/tools are *advertised* in a lightweight index and loaded only when the agent determines they are needed for the current task:

```
advertise → agent decides relevance → load → read → run
```

This keeps the active context window fresh and the agent in control of what it knows, rather than a fixed pipeline deciding for it. Add a skill when a capability is genuinely reusable; don't create one for a one-off task.

## The SKILL.md Format

> Source: [Microsoft Agent Framework — Skills](https://learn.microsoft.com/en-us/agent-framework/agents/skills)

A Skill is a self-contained, portable unit of agent capability — a directory that bundles everything the agent needs on demand, without pre-loading it all into context.

### Structure

```
<skill-name>/
├── SKILL.md          # Required — frontmatter + natural-language instructions
├── scripts/          # Executable code the agent can invoke via run_skill_script
├── references/       # Reference docs loaded on demand via read_skill_resource
└── assets/           # Templates, examples, static resources
```

### Frontmatter Fields

```yaml
---
name: skill-name
description: What the skill does and when to use it. Max 1024 chars. Include task keywords.
license: Apache-2.0
compatibility: Requires python3
metadata:
  author: your-team
  version: "1.0"
allowed-tools: tool_one tool_two
---
```

| Field | Required | Rules |
|---|---|---|
| `name` | Yes | Max 64 chars. Lowercase, numbers, hyphens only. Must match parent directory name. |
| `description` | Yes | What it does and **when to use it** — shown at advertise stage (~100 tokens). Include trigger keywords. |
| `license` | No | License name or reference to bundled license file. |
| `compatibility` | No | Max 500 chars. Environment requirements (OS, packages, network access). |
| `metadata` | No | Arbitrary key-value pairs (author, version, team). |
| `allowed-tools` | No | Space-delimited pre-approved tools the skill may call. Experimental. |

### Progressive Disclosure — 4 Stages

The agent loads only what it needs, when it needs it:

| Stage | Tokens | What happens |
|---|---|---|
| **Advertise** | ~100 per skill | Skill names + descriptions injected into system prompt at run start. |
| **Load** | < 5000 recommended | Agent calls `load_skill` when a task matches — full SKILL.md body arrives. |
| **Read resources** | as needed | Agent calls `read_skill_resource` to fetch from `references/` or `assets/`. |
| **Run scripts** | as needed | Agent calls `run_skill_script` to execute from `scripts/`. |

`load_skill` is always advertised. `read_skill_resource` only if the skill has resources. `run_skill_script` only if the skill has scripts.

### 11 Skill Authoring Patterns

A single SKILL.md can combine several of these:

| # | Type | What it does |
|---|---|---|
| 1 | **Instructional** | Step-by-step guidance, rules, output format, edge cases — the classic SKILL.md. |
| 2 | **Workflow / Procedural** | Defines a multi-step process the agent must follow in order. |
| 3 | **Domain Expertise** | Packages specialized knowledge (finance rules, legal workflows, data pipelines). |
| 4 | **Task-Specific** | Narrow, trigger-matched skills that only activate for one task. |
| 5 | **Tool-Usage** | Teaches the agent to invoke deterministic scripts rather than reason through the answer. |
| 6 | **Reference / Context** | Provides supporting docs (FAQ, policy, schema) loaded on demand from `references/`. |
| 7 | **Few-Shot / Example-Driven** | Uses concrete input → output examples in `assets/` instead of verbose instructions. |
| 8 | **Decision-Framework** | Teaches the agent *how to think*: heuristics, prioritization, review methodology. |
| 9 | **Role-Definition** | Defines a persona the agent should adopt (architect, reviewer, security auditor). |
| 10 | **Template-Driven** | Provides scaffolds the agent fills in: component templates, test skeletons, report formats. |
| 11 | **Composite / Multi-File** | Full capability package combining scripts, examples, references, and templates. |

**Key insight:** Use a **script** (pattern 5) whenever the answer is binary (pass/fail, valid/invalid) — LLMs are unreliable for rules requiring exact matching. Use **examples** (pattern 7) when the task involves implicit style decisions that are hard to express in text.

## Directory Structure

```
.agents/                          # SOURCE OF TRUTH (committed to Git)
├── README.md                     # This file — copy to any new repo
├── AGENT.md                      # Tool-agnostic guidelines for AI assistants
├── AGENTS.md                     # Tool-specific overrides (optional)
├── cursor/
│   └── rules/                    # Cursor IDE rules (source)
└── skills/                       # Agent Skills, added as needed
```

## Symlinks

Each AI tool expects its config in a specific location. Symlinks keep everything in sync without duplicating files:

| Symlink (repo root)   | Points to                  | Tool(s)                      |
|-----------------------|----------------------------|------------------------------|
| `.cursor/rules/`      | `.agents/cursor/rules/`    | Cursor IDE                   |
| `skills/`             | `.agents/skills/`          | Claude Code, VS Code Copilot |
| `AGENT.md`            | `.agents/AGENT.md`         | Claude Code, generic tools   |
| `AGENTS.md`           | `.agents/AGENTS.md`        | OpenAI Codex, generic tools  |

## Root repository symlinks

This repository also keeps root-level aliases for convenience and compatibility:

- `SKILLS` → `.agents/SKILLS`
- `AGENT.md` → `.agents/AGENT.md`

These are already created in `c:\dev\tts` so tools and humans can access the agent config from the repo root.

## Local Git hooks

This repo uses `.githooks/` to enforce commit hygiene and block AI agent trailer attribution.
Enable it with:

```bash
git config core.hooksPath .githooks
```

## Setup for a New Repo

```bash
# From the repo root
mkdir -p .agents/cursor/rules .agents/skills
mkdir -p .cursor

# Symlinks
ln -sf .agents/cursor/rules .cursor/rules
ln -sf .agents/skills skills
ln -sf .agents/AGENT.md AGENT.md
ln -sf .agents/AGENTS.md AGENTS.md

# Copy this README into the new repo
cp .agents/README.md <new-repo>/.agents/README.md
```

> **Windows:** enable symlinks before running — either turn on Developer Mode or run `git config core.symlinks true`.
