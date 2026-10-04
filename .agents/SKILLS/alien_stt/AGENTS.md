# AGENTS.md: alien_stt skill

This folder is a **self-sufficient unit**: everything the AlienSTT skill needs
lives inside it. The library is vendored at `./alienstt/`; scripts import it by
path (`sys.path` set from the script's own location), so the folder works wherever
it is copied. No sibling repo, no `pip install` of this skill itself.

## Copying to a new machine or repo

1. Copy `alien_stt/` whole, or run `python build.py` and unzip `.build/alien_stt.zip`.
2. Create a venv inside it and `pip install -r scripts/requirements.txt`.
3. Install ffmpeg/ffprobe on `PATH`.
4. `python scripts/check_setup.py`, then `python -m pytest tests -v`.

## Ownership and links

This folder lives in the repository that owns it; any other location that
exposes it (a host project's `SKILLS/alien_stt`, a personal skills folder) should
be a link to it, not a copy. Before changing a link, inspect its target. Never
delete this folder to "replace a link".

## Conventions

- **Thin scripts.** `scripts/*.py` parse arguments, call the library, report. Real
  logic lives in `alienstt/`. If two scripts need the same code, it moves into the
  library (or `alienstt/cli.py`), never gets pasted twice.
- **Layering.** `base` -> `device` -> `audio` -> `postprocess` -> `formats` ->
  `trace` -> `engines` -> `pipeline`. A module imports only from earlier ones.
  Only `engines/*` may import torch or transformers, and only inside functions.
- **One engine contract.** New speech backends implement `alienstt.base.SttEngine`
  and register in `alienstt/engines/__init__.py`. Nothing else should name a
  concrete engine.
- **Verbose in-code documentation.** Every module opens with a docstring that
  says what the module is for, *why* it is designed that way, and the failure it
  guards against; every public function documents parameters, return, raised
  errors and non-obvious behaviour. Comments explain reasons, not syntax. Update
  docs in the same change as the code. Scripts open with usage examples and exit
  codes.
- **Safe by default.** No overwrite without a flag; atomic writes; sources never
  modified; `--dry-run` where a script writes; a non-zero exit with a message on
  failure, never a silent one.
- **No personal data, no host specifics.** No names, paths, accounts or project
  vocabulary in code, docs, fixtures or examples. No hard-coded install paths.
  Locations come from arguments or environment variables.
- **Skip, never download, in tests.** Tests are real (real ffmpeg, real audio,
  real model) and skip with a reason when a prerequisite is absent.
- **Dates and stamps.** DATETIME STAMP is `YYYYMMDDHHmmss` in Pacific time. The
  version in `SKILL.md` frontmatter is `Major.Minor.<DATETIME STAMP>`; bump it when
  behaviour, outputs, supported environments or safety posture change, not for
  reformatting.
- **Ambitions go in `docs/ROADMAP.md`**, never in the `description` or in present
  tense in `SKILL.md`. Add a capability to the description in the same change that
  adds the capability.
- **Keep the registry honest.** The skills registry that lists this skill, and
  `SKILL.md`'s jobs, must agree; when they drift, `SKILL.md` is right.

## Before landing a change

Run `python -m pytest tests -v` (all real tests, with the model cached) and
`python scripts/check_setup.py`. `tests/test_skill_contract.py` checks the
authoring checklist mechanically: name matches folder, description length, local
links exist, no absolute paths, every script answers `--help`. Fix failures; do
not skip them.
