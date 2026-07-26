# Dev / Prod Reference

## Purpose

Use this reference when a change touches install flow, packaging, deployment, config files, or any place where the dev machine and the shipped product must behave differently.

## Operating Philosophy

- Dev may tolerate redundancy, extra diagnostics, and temporary experimental paths.
- Prod must be predictable, minimal, and safe for non-technical users.
- Do not let a dev convenience leak into prod unless it is intentionally part of the product.
- Prefer one-way data flow: bundle defaults, copy them into user space, then let runtime mutate only user-owned state.
- Avoid the Windows registry as the primary config store when a cross-platform file-based path will work.

## Canonical File Roles

### Bundled defaults

- Source: checked into the repo.
- Copied during install/build.
- Read-only for the shipped app.
- Example: supported stacks/models/voices catalog.

### User config

- Lives in a per-user writable location.
- May differ between dev and installed builds.
- Stores user choices, overrides, and runtime state.
- Must never be rewritten into bundled source files.

### Install assets

- Live under the installer tree or shipped artifact tree.
- Include preview audio, icons, templates, and other static distributable files.
- May be generated during setup/build.
- Are not model weights.

### Model weights

- Large runtime downloads.
- Can be absent in a fresh install.
- Install/uninstall should manage these separately from preview assets.

## Current AlienVox Guidance

### Development

- Prefer repo-local defaults for reproducibility.
- Keep generated assets in a deterministic location under the repo during development if they are not yet packaged.
- Allow experiments and extra logging when they help diagnose behavior.

### Production

- Copy the bundled default config into the user install location.
- Keep preview assets available even when model weights are missing.
- Keep user config and runtime caches in their own writable location.
- Keep UI behavior crisp: the app should not need to guess where defaults came from.

## Path Decisions

When deciding where a file should live, ask:

1. Is it a shipped default or a user-owned override?
2. Is it static install-time content or runtime-generated state?
3. Does uninstall need to preserve it?
4. Should it survive model removal?
5. Is it safe to share across all installs or should it be per-user?

## Good Patterns

- Copy the default catalog during install, then load that copied catalog at runtime.
- Reference preview samples from the catalog, but store the audio files as install assets.
- Keep uninstall limited to model weights unless the user explicitly asks to remove assets.
- Let the app discover installed models from the file system, but let supported voices come from config.

## Bad Patterns

- Writing user choices back into bundled source files.
- Hiding missing model files by deleting the voice from the catalog.
- Using registry lookups as the primary config mechanism for cross-platform behavior.
- Coupling install assets to runtime downloads so uninstall destroys previews.
- Making prod behavior depend on dev-only cache paths.

## When To Update This Reference

- New installer mode or install step
- New config location or app-data path
- New model/voice packaging behavior
- New platform-specific deployment rule
- Any change that affects how the app distinguishes dev from prod
