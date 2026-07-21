# TODO #004: Auto-Enhance Text Before TTS

**Status:** Strategy A (heuristic) and Strategy B (LLM, ADR-012 resolved) both shipped as a
dedicated "Play Enhanced" action  
**Updated:** 2026-07-21  
**Scope:** `src/control/text_enhancer.py`, `src/control/app_controller.py`, `src/view/main_window.py`,
`src/resources/prompts/enhance_for_tts.txt`

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

## Implementation status (2026-07-21)

Both strategies are implemented as a **dedicated one-shot action**, not a persisted mode — this
differs from the original design below (a toolbar toggle backed by an `AppState` field), which was
tried first and then deliberately reverted in favor of a simpler shape: a second "Play Enhanced"
button next to the regular Play button, using `resources/icons/play_enhanced.png`.

- `AppController.play_enhanced_async(text)` — the command a View calls; spawns the same
  `speak(text, restart=True, enhance="heuristic")` path as `play_async`, just with `enhance` set.
  Currently hardcodes `"heuristic"` — see "Not done" below for why LLM isn't the default yet.
  There is no `AppState.enhance_strategy` field — enhancement is a per-call argument to
  `AppController.speak()`, not state that could drift or need syncing across Views. This is why the
  MVC controller-command convention (`.agents/SKILLS/highlevel_design/SKILL.md` §7.2) still applies
  even though there's no new `AppState` field this time: **not every new action needs new state** —
  a one-shot action just needs a Controller command a View can call.
- `AppController._enhance_text(text, strategy)` — applies the requested strategy, **falling back to
  heuristic** (never to raw text) if `strategy == "llm"` raises (model load failure, empty output,
  speaker-tag count mismatch, or implausible output length — see `llm_enhance`'s validation).
  Telemetry records `enhance_strategy` as `"llm_fallback_heuristic"` when this happens,
  distinguishable from a deliberate heuristic choice.
- `text_enhancer.llm_enhance(text, prompt_path=None)` — loads the GGUF model (lazy singleton,
  thread-safe via a lock), sends `resources/prompts/enhance_for_tts.txt` as the system prompt plus
  the raw text as the user message, and validates the response before returning it: non-empty,
  same `[S1]`/`[S2]` tag count as the input, and output length within 0.3x–3x of input length.
  Any validation failure raises `RuntimeError`, triggering the Controller's fallback.
- `MainWindow` toolbar has two buttons side by side: `_btn_play` (unchanged, speaks as-is) and
  `_btn_play_enhanced` (uses `play_enhanced.png`, calls `play_enhanced_async`). Regular Play is
  completely unaffected by the enhanced button existing.
- `heuristic_enhance()` preserves Dia's `[S1]`/`[S2]` tags via a stash/restore pass before any rule
  runs; `llm_enhance()` preserves them via prompt instruction + post-hoc tag-count validation.
- Tests: `tests/test_text_enhancer.py` mocks `_get_llm()` so the LLM-path tests run in milliseconds
  with no network/model dependency (covers success, empty output, tag mismatch, implausible length,
  custom prompt file). `tests/test_app_controller.py` mocks `text_enhancer.llm_enhance` itself to
  test the Controller's fallback wiring in isolation from model behavior.

**Not done:**
- Export path (`audio_exporter.py`) doesn't call `enhance()` yet.
- `play_enhanced_async` still hardcodes `enhance="heuristic"` rather than `"llm"` — LLM enhancement
  works but adds real latency (model load + inference) and a ~470MB one-time download, so making it
  the default for a single button needs a product decision (a loading indicator? a third button?
  user-visible download consent?), not just a code change. Tracked as open follow-up, not blocking.

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
