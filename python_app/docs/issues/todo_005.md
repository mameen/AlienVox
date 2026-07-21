# TODO #005: CLI Surface Sharing AppController with the GUI

**Status:** Open  
**Updated:** 2026-07-21  
**Scope:** `run.py`, `src/control/app_controller.py`

---

## Problem

`run.py` currently only has `app` (launch the GUI) and `download` subcommands. There is no way to
drive AlienVox from the command line (`run.py speak "text"`, `run.py stop`, `run.py set-voice
kokoro:af_heart`) without going through the tray/window.

This was originally scoped as part of the MVC migration (see `adr-004-mvc-architecture.md`) but was
dropped from that change to keep it focused on fixing the model/voice desync bug. The MVC split
(`AppState` + `AppController`) that's now in place makes this straightforward to add later:
`AppController` already has zero Qt dependency in its command surface (`select_stack`,
`select_model`, `select_voice`, `update_params`, `speak`/`stop`, `save_settings_to`/
`load_settings_from`) — a `CliView` just needs to construct an `AppState`/`AppController` pair
without a `QApplication` and call the same methods the GUI does.

## Why it matters

- Scripting (`run.py speak "..." --voice af_heart`) is a natural ask for a tray-first utility.
- Testing `AppController` end-to-end without spinning up Qt widgets becomes easier once there's a
  real non-GUI caller exercising it, not just unit tests with a fake engine.

## Suggested approach

1. Add a `speak`/`stop`/`set-voice` subcommand group to `run.py`.
2. Each subcommand: build `AppState` from `load_effective_config()` + `available_stacks()` (same as
   `main.py`), build `AppController`, call the relevant method, print a one-line result, exit.
3. No event loop needed for one-shot commands — `AppController.speak()` is synchronous when called
   directly (only `speak_async`/`play_async` spawn threads, and those exist for the GUI's benefit).
4. Skip this for anything that needs live state across multiple invocations (e.g. "toggle speaking
   from another process") — that needs IPC into the already-running instance, a separate and bigger
   problem tracked separately if it comes up.

Not estimated in detail — pick up when there's an actual scripting use case, not speculatively.
