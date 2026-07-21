# TODO #004: Auto-Enhance Text Before TTS

**Status:** Strategy A (heuristic) and Strategy B (LLM, ADR-012 resolved) both shipped, as a
**global, persisted toggle** — third design iteration, see "Design history" below  
**Updated:** 2026-07-21  
**Scope:** `src/model/app_state.py`, `src/control/app_controller.py`, `src/view/main_window.py`,
`src/view/toggle_switch.py`, `src/control/text_enhancer.py`, `src/resources/prompts/enhance_for_tts.txt`

---

## Design history (for context on the code below)

This feature's UI shape changed twice during implementation, each time on explicit developer
request — recorded here so the "why" survives, not just the current state:

1. **First**: a persisted `AppState.enhance_strategy` toggle in the toolbar.
2. **Then**: reverted to a dedicated one-shot "Play Enhanced" button/hotkey — the reasoning at the
   time was "not every new action needs new state," and `AppState.enhance_strategy` was removed.
3. **Finally (current)**: back to a persisted global toggle (`AppState.enhance_strategy` re-added),
   this time explicitly wired into Export too, and using a shared `ToggleSwitch` widget everywhere
   the app needs an on/off control (this toggle, and the per-voice enable/disable in the Settings
   dialog) instead of a checkbox or a plain checkable button.

---

## ADR-012 resolution (2026-07-21)

**Selected: Qwen2.5-0.5B-Instruct**, GGUF `q4_k_m` quantization, via `llama-cpp-python` (in-process,
no subprocess — required by `SKILL.md` §3). Repo: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`, file
`qwen2.5-0.5b-instruct-q4_k_m.gguf` (~470MB). Chosen over Phi-3-mini per the original cost table in
this doc: smaller download, lower VRAM/RAM, faster — "good enough" bar for a delivery-cleanup task,
not a task that needs Phi-3-mini's extra reasoning capacity.

Verified working end-to-end in this environment: the model downloads to `.models/text_enhancer/`
on first use (`huggingface_hub.hf_hub_download`, cached after), loads via `llama_cpp.Llama`, and
`create_chat_completion` returns real output — confirmed via the test suite actually triggering a
real download+load+inference the first time (before `llm_enhance` was properly mocked in
`test_app_controller.py`; see git history if curious).

## Implementation status (2026-07-21, current design)

Both strategies are wired through a **global, persisted toggle** in the toolbar — flipping it
affects every subsequent Play click, the global hotkey, the tray, and Export, until flipped back.

- `AppState.enhance_strategy` (`"none" | "heuristic" | "llm"`) — persisted field, setter, signal
  (`enhance_strategy_changed`), like every other user-facing setting.
- `AppController.select_enhance_strategy(strategy)` — the command the toolbar toggle calls.
- `AppController.speak(text, restart, enhance=None)` — `enhance=None` (the default used by
  `play_async`/`speak_async`, i.e. Play/hotkey/tray) means "use `state.enhance_strategy`," resolved
  inside `_speak_locked` at call time. An explicit `"none"`/`"heuristic"`/`"llm"` overrides the
  toggle for that call only — used by `play_sample_async`, which always passes `"none"` explicitly
  so the diagnostic sample phrase stays deterministic regardless of the toggle (also keeps
  testing/perf benchmarking deterministic, since neither touches this state).
- `AppController.apply_current_enhance(text)` — applies `state.enhance_strategy` to arbitrary text;
  `MainWindow._on_export` calls this before constructing `ExportDialog`, so exported audio matches
  whatever Play would currently speak.
- `AppController._enhance_text(text, strategy)` — unchanged: applies the requested strategy,
  **falling back to heuristic** (never to raw text) if `strategy == "llm"` raises (model load
  failure, empty output, speaker-tag count mismatch, or implausible output length — see
  `llm_enhance`'s validation). Telemetry records `enhance_strategy` as `"llm_fallback_heuristic"`
  when this happens.
- `MainWindow` toolbar has a labeled `ToggleSwitch` ("Enhanced") next to Play/Pause/Stop — see
  `src/view/toggle_switch.py`, a small reusable custom-painted on/off switch (PySide6/QtWidgets has
  no built-in one) used here and for per-voice enable/disable in the Settings dialog, so every
  toggle in the app looks and behaves the same.
- `heuristic_enhance()` preserves Dia's `[S1]`/`[S2]` tags via a stash/restore pass before any rule
  runs; `llm_enhance()` preserves them via prompt instruction + post-hoc tag-count validation.
- Tests: `tests/test_text_enhancer.py` mocks `_get_llm()` so the LLM-path tests run in milliseconds
  with no network/model dependency. `tests/test_app_controller.py` covers the `enhance=None`
  resolution, the explicit-override path, `apply_current_enhance`, and that `play_sample_async`
  stays unenhanced even with the toggle on.

**Still open:** the toggle only offers heuristic (`"heuristic"`, not `"llm"`) — flipping it to use
the LLM strategy by default needs a product decision around latency (model load + inference isn't
instant) and the one-time ~470MB download, not just a code change. `select_enhance_strategy` already
accepts `"llm"`, so this is a UI-only follow-up when that decision is made.

## Known limitation: heuristic strategy does not fix prosody/pacing issues

`heuristic_enhance()` only touches whitespace and punctuation — it cannot restructure a sentence,
so it does nothing for pauses caused by run-on sentences, awkward clause ordering, or missing
commas the source text never had a hint of (nothing for it to normalize). Observed directly in
production telemetry on 2026-07-21: a 325-character input produced a 326-character
`heuristic_enhance()` output (`text_chars: 325` → `enhanced_chars: 326`, `enhance_strategy:
"heuristic"`) — effectively a single added character (a missing terminal period), while the user
still reported "weird pauses" in playback. This confirms the heuristic strategy is not a fix for
prosody-level pacing problems; that gap is exactly what the LLM strategy (now implemented, see ADR-012
resolution above) exists to close, but `play_enhanced_async` doesn't route to it by default yet
(see "Not done" above).

---

## Problem

Raw text passed to TTS engines produces unnatural, halting speech due to formatting
artifacts that have no spoken equivalent:

- **Excessive blank lines / whitespace** — multiple newlines become long pauses; mid-sentence
  double spaces create micro-pauses that break rhythm
- **Punctuation collisions** — `...` read as three separate dots; `–` and `—` cause engine
  confusion; `,,,` or `???` produce stuttering
- **Repeated punctuation** — `!!!` or `???` makes some engines repeat the exclamation phoneme
- **Mid-word hyphens in non-compound words** — `some-thing` spoken as "some hyphen thing"
- **Stray symbols** — `|`, `>`, `~`, `^` copied from tables or terminals are read literally
- **No sentence boundary after paragraphs** — two consecutive sentences with only a newline
  between them run together without a natural pause

Markdown rendering and code blocks are a **separate concern** — handled at the editor layer
(the `_MultiFormatEditor` renders Markdown as HTML and hands the engine clean plain text;
see below). The enhancer only sees plain text by the time it runs.

---

## Separation of Concerns

```
User pastes text into editor
        │
        ▼
_MultiFormatEditor  ←── Renders Markdown/HTML visually; to_plain_text()
        │                strips formatting tags before handing off
        ▼
text_enhancer.enhance()  ←── Fixes whitespace & punctuation for fluent speech
        │
        ▼
engine.speak() / synthesize()
```

**Editor layer** (todo_001, already partially done):
- Markdown pasted → rendered as HTML in `QTextEdit` (visual, not raw)
- `to_plain_text()` already calls `QTextEdit.toPlainText()` which strips HTML tags
- **Gap**: Markdown pasted as plain text (not loaded from `.md` file) is not auto-detected
  and rendered — the user sees raw `**bold**`. Consider auto-detecting and converting.

**Enhancer layer** (this todo):
- Receives plain text only
- Fixes prosody-breaking whitespace and punctuation
- Does NOT need to know about Markdown at all

---

## Proposed Solution

*(Original proposal below — superseded by "Implementation status" above: shipped as a dedicated
"Play Enhanced" button rather than a persisted toggle. Kept for historical context and because the
Strategy A/B split and cost comparison still hold.)*

### UI

A small **"Auto-enhance"** toggle in the main window toolbar (pill/toggle style).  
Default: **off** (opt-in — power users keep full control).  
State persisted in `user.yaml` as `auto_enhance: true/false`.

### Architecture

`src/text_enhancer.py` — composable, two strategies:

#### Strategy A — Heuristic (always available, zero latency)

Pure Python, no dependencies. Fast enough to be invisible. Focused on **whitespace and punctuation**:

| Rule | Example in → out | Rationale |
|------|-----------------|-----------|
| Collapse 3+ consecutive blank lines → 1 | `\n\n\n\n` → `\n\n` | Removes ultra-long silences |
| Collapse 2+ spaces within a line → 1 | `foo  bar` → `foo bar` | Micro-pause elimination |
| Strip trailing whitespace per line | `"hello   \n"` → `"hello\n"` | Clean sentence ends |
| Ensure paragraph ends with `.` if no terminal punct | `"Go now\n\nThen stop"` → `"Go now.\n\nThen stop"` | Natural sentence break |
| Collapse repeated punctuation | `"Really???  !!!"` → `"Really? !"` | Engine stutter guard |
| Normalise ellipsis | `"Well..."` → `"Well…"` or `"Well, "` | Single pause beat |
| En-dash / em-dash → comma-space | `"cats – dogs"` → `"cats, dogs"` | Natural spoken pause |
| Strip lone non-alphanumeric lines | a line containing only `| --- |` or `~~~` | Table/HR artifacts |
| Trim leading blank lines at document start | `\n\nHello` → `Hello` | No leading silence |
| Trim trailing blank lines at document end | `Hello\n\n\n` → `Hello` | No trailing silence |

All rules in one function `heuristic_enhance(text: str) -> str`. No regex soup —
each rule is named and isolated so tests map 1-to-1.

#### Strategy B — LLM (optional, zero-latency is not guaranteed)

A small instruction-tuned model rewrites text for natural spoken delivery.
The system prompt lives in a separate file so it can be tuned without touching Python:

```
src/prompts/enhance_for_tts.txt
```

Candidate models (all on-device):
- `Qwen2.5-0.5B-Instruct` GGUF via `llama-cpp-python` (~400 MB) — fastest
- `Phi-3-mini` (3.8B) — higher quality

LLM path activated when `enhance_strategy: llm` in `user.yaml`. Default: `heuristic`.

### Text Enhancer API

```python
# src/text_enhancer.py

def heuristic_enhance(text: str) -> str:
    """Fast rule-based whitespace/punctuation cleanup. Zero dependencies."""
    ...

def llm_enhance(text: str, prompt_path: Path | None = None) -> str:
    """LLM rewrite for natural speech. Raises NotImplementedError until ADR-012."""
    raise NotImplementedError("LLM enhancer pending ADR-012 model selection")

def enhance(text: str, strategy: str = "heuristic") -> str:
    """Entry point. strategy: 'heuristic' | 'llm' | 'none'."""
    if strategy == "none":
        return text
    if strategy == "llm":
        return llm_enhance(text)
    return heuristic_enhance(text)
```

---

## Cost Comparison

Estimates for a typical paste: **500 characters / ~100 words** of messy text.

| Dimension | Strategy A — Heuristic | Strategy B — LLM (Qwen 0.5B) | Strategy B — LLM (Phi-3-mini 3.8B) |
|-----------|----------------------|------------------------------|--------------------------------------|
| **Execution time** | < 1 ms | 300 – 800 ms (GPU) / 2 – 5 s (CPU) | 1 – 3 s (GPU) / 8 – 20 s (CPU) |
| **First-call overhead** | 0 (no load) | ~3 s model load (cached after) | ~8 s model load (cached after) |
| **Tokens consumed** | 0 | ~150 in + ~150 out ≈ 300 tok | ~150 in + ~150 out ≈ 300 tok |
| **VRAM** | 0 | ~600 MB | ~3.5 GB |
| **RAM (CPU fallback)** | 0 | ~800 MB | ~5 GB |
| **Network** | None | None (on-device) | None (on-device) |
| **Dependencies added** | 0 | `llama-cpp-python` (~50 MB wheel) + GGUF model file | same |
| **Model download size** | 0 | ~400 MB (one-time) | ~2.3 GB (one-time) |
| **Lines of code** | ~60 (rules + tests) | ~40 (loader + call) + prompt file | same |
| **Test complexity** | Low — deterministic, one test per rule | High — output is probabilistic; hard to assert exact strings |
| **Failure modes** | None (pure string ops) | Model OOM, slow CPU, hallucinated output, prompt injection risk |
| **Correctness** | Predictable — rules do exactly what they say | Variable — may over-rewrite, change meaning, or miss subtle issues |
| **Latency user perceives** | Invisible (batched with speak()) | Noticeable pause before speech starts (especially CPU) |
| **Maintainability** | High — rules are readable prose in code | Medium — behaviour changes when prompt or model changes |

### Recommendation

Ship **Strategy A only** for v1. It covers the core problem (whitespace/punctuation) with zero
cost and zero risk. Strategy B becomes worthwhile only if user testing shows heuristics miss
cases that genuinely matter — at which point ADR-012 selects the model.

The toggle UI and `enhance()` entry point are already designed to swap strategies without
touching `main.py` or the engine layer.

---

## Telemetry

When `auto_enhance` is on, emit both original and enhanced char counts:

```json
{
  "event": "speak.triggered",
  "text_chars": 240,
  "text_bytes": 480,
  "enhanced_chars": 198,
  "enhanced_bytes": 396,
  "enhance_strategy": "heuristic"
}
```

**Security constraint (unchanged):** Never record the source text itself — only sizes and strategy.

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `src/text_enhancer.py` | New — heuristic + LLM stub |
| `src/prompts/enhance_for_tts.txt` | New — LLM system prompt |
| `src/main_window.py` | Add toggle to toolbar; persist to `user.yaml` |
| `src/main.py` | Call `enhance()` before `engine.speak()` and before export |
| `src/telemetry.py` | Add `enhanced_chars`, `enhanced_bytes`, `enhance_strategy` fields |

---

## Open Questions / ADR Candidates

- **ADR-012 — RESOLVED**: Qwen2.5-0.5B-Instruct GGUF via `llama-cpp-python`. See "ADR-012
  resolution" above.
- Should `play_enhanced_async` default to `"llm"` instead of `"heuristic"` now that it's real? Not
  done yet — see "Not done" above (latency/download-consent product question, not a code blocker).
- Should the toggle be per-engine? (Dia uses `[S1]`/`[S2]` tags — both strategies must not touch them)
- Should heuristic rules be user-configurable checkboxes in Preferences?
- Should we auto-detect Markdown pasted as plain text and render it? (Editor-layer gap noted above)

---

## Acceptance Criteria

- [x] `heuristic_enhance()` covered by `tests/test_text_enhancer.py` — one test per rule minimum
- [x] Dedicated "Play Enhanced" button visible in toolbar next to Play (`play_enhanced.png`)
- [x] `enhance()` called via `AppController.play_enhanced_async` → `speak(enhance="heuristic")` before
      `engine.speak()` — regular Play stays un-enhanced (`tests/test_app_controller.py`)
- [ ] `enhance()` called in `audio_exporter.py` before synthesis (export path not wired yet)
- [x] Telemetry emits `enhanced_chars`/`enhanced_bytes`/`enhance_strategy` only when `enhance != "none"`
- [x] LLM path (`llm_enhance`) implemented and verified working (real download + inference confirmed
      during test development) — ADR-012 resolved; validates output before returning it and falls
      back to heuristic on any failure
- [x] Heuristic does NOT strip or modify `[S1]`/`[S2]` Dia speaker tags; LLM path validates tag count
      unchanged and falls back to heuristic if it drifts
