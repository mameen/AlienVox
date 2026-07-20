# TODO #004: Auto-Enhance Text Before TTS

**Status:** Open  
**Updated:** 2026-07-20  
**Scope:** `src/text_enhancer.py` (new), `src/main_window.py`, `src/main.py`, `src/telemetry.py`

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

- **ADR-012**: Which local LLM for strategy B? (Qwen 0.5B vs Phi-3-mini)
- Should the toggle be per-engine? (Dia uses `[S1]`/`[S2]` tags — heuristic must not touch them)
- Should heuristic rules be user-configurable checkboxes in Preferences?
- Should we auto-detect Markdown pasted as plain text and render it? (Editor-layer gap noted above)

---

## Acceptance Criteria

- [ ] `heuristic_enhance()` covered by `tests/test_text_enhancer.py` — one test per rule minimum
- [ ] Toggle visible in toolbar; state survives restart
- [ ] `enhance()` called in `main.py` before `engine.speak()` when toggle is on
- [ ] `enhance()` called in `audio_exporter.py` before synthesis when toggle is on
- [ ] Telemetry emits `enhanced_chars` only when `auto_enhance` is on
- [ ] LLM path raises `NotImplementedError` until ADR-012 is resolved
- [ ] Heuristic does NOT strip or modify `[S1]`/`[S2]` Dia speaker tags
