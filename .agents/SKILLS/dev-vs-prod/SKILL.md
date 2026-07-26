---
name: dev-vs-prod
description: Dev/prod environment guidance for AlienVox. Use when a task touches installation, packaging, config file locations, dev vs production differences, portable vs installed builds, user config paths, deployment behavior, or when deciding what belongs in source control versus generated assets.
---

# Dev Vs Prod

## Overview

Keep the repo split sharp:

- Dev mode is allowed to be redundant, experimental, and a bit forgiving.
- Prod mode must be crisp, deterministic, and user-facing stable.
- Never assume the same file path, config source, or install behavior applies to both.

## Core Rules

1. Treat the bundled catalog as the single source of truth for supported stacks, models, and voices.
2. Keep user-editable config separate from bundled defaults.
3. Keep generated samples and installer assets separate from model weights.
4. Prefer explicit file locations over implicit discovery.
5. Avoid registry-based state for cross-platform config or installation logic unless a Windows-only API truly requires it.

## Read First

When a task touches install, packaging, or deployment, read the detailed reference in:

- [`references/dev_prod_reference.md`](references/dev_prod_reference.md)

That reference is the detailed contract for:

- where user config lives in dev and prod
- where bundled defaults live
- where install assets live
- what the installer should copy
- what the runtime may mutate
- what must never be written back into source control

## Use This Skill For

- adding or changing installer behavior
- deciding whether a file belongs in source control, install assets, or user data
- reconciling dev and prod path differences
- documenting deployment or packaging workflows
- adding new platform-specific install rules
- designing one-way data flow for configuration and catalog state

## Execution Guidance

- Recommend the safest default first, then the more advanced option.
- If dev can accept extra flexibility but prod cannot, design the API so the stricter prod rule is still easy to satisfy.
- If a task needs platform-specific branching, make the decision at the boundary and keep the inner logic shared.
- When in doubt, prefer a manifest or config file over scattered hardcoded lists.

## Common Decision Pattern

- Bundled defaults: checked in, copied during install.
- User config: stored per user/per install location, never hardcoded into Views.
- Generated previews: can be built during setup, then shipped as install assets.
- Model weights: installable at runtime, but not required for the basic app shell.
