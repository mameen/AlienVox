# TODO #004: Auto-Enhance Text Before TTS

**Status:** Open  
**Updated:** 2026-07-20  
**Scope:** `src/text_enhancer.py` (new), `src/main_window.py`, `src/main.py`, `src/telemetry.py`

---

## Problem

Raw text passed to TTS engines is often poorly formatted for spoken output:

- Accidental double spaces, trailing newlines, or stray blank lines cause audible pauses
- Markdown formatting (`**bold**`, `# Heading`, `` `code` ``) is read literally
- URLs and file paths are read character-by-character
- Abbreviations (`e.g.`, `etc.`, `vs.`) trigger incorrect sentence breaks
- Code snippets, JSON, or log lines produce meaningless robotic output
- Multiple consecutive blank lines cause long uncomfortable silences
- Bullet point markers (`-`, `*`, `•`) are spoken aloud

These are common because users paste from editors, browsers, docs, and terminals.

---

## Proposed Solution

### UI

A small **"Auto-enhance"** toggle in the main window toolbar (pill/toggle style, like the screenshot).  
Default: **off** (opt-in, so power users keep full control).  
State persisted in `user.yaml` as `auto_enhance: true/false`.

### Architecture

A composable `src/text_enhancer.py` module with two enhancement strategies, selectable independently:

#### Strategy A — Heuristic (always available, zero latency)

Pure Python text normalization. Fast enough to be invisible. Covers:

| Rule | Example in → out |
|------|-----------------|
| Collapse 3+ blank lines → 1 | `\n\n\n\n` → `\n\n` |
| Strip leading/trailing whitespace per paragraph | `"  hello  "` → `"hello"` |
| Collapse mid-sentence multiple spaces | `"foo  bar"` → `"foo bar"` |
| Strip Markdown headings `#` prefix | `# Title` → `Title` |
| Strip Markdown bold/italic (`**`, `*`, `__`, `_`) | `**bold**` → `bold` |
| Strip inline code backticks | `` `code` `` → `code` |
| Strip fenced code blocks entirely | ` ```\n...\n``` ` → `[code block]` |
| Expand common abbreviations | `e.g.` → `for example`, `etc.` → `and so on` |
| Strip bullet markers | `- item` → `item` |
| Normalize URL to domain only | `https://github.com/foo/bar` → `github.com` |
| Strip email angle brackets | `<user@host>` → `user@host` |

All rules live in one function `heuristic_enhance(text: str) -> str` — easy to unit-test.

#### Strategy B — LLM (optional, async, requires local model or API)

A small language model rewrites the text for natural spoken delivery. The prompt is stored in a separate file:

```
src/prompts/enhance_for_tts.txt
```

This allows the prompt to be tuned without touching Python code.

Candidate models (all on-device, no internet required at inference time):
- `Qwen2.5-0.5B-Instruct` (GGUF via llama-cpp-python, ~400 MB) — fastest
- `Phi-3-mini` (3.8B) — higher quality
- `Kokoro` itself cannot rewrite text, but any instruction-tuned model can

The LLM path is only activated when `enhance_strategy: llm` in `user.yaml`. Default strategy is `heuristic`.

### Text Enhancer API

```python
# src/text_enhancer.py

def heuristic_enhance(text: str) -> str:
    """Fast rule-based cleanup. Zero dependencies."""
    ...

async def llm_enhance(text: str, prompt_path: Path | None = None) -> str:
    """LLM rewrite for natural speech. Loads model on first call."""
    ...

def enhance(text: str, strategy: str = "heuristic", **kwargs) -> str:
    """Entry point. strategy: 'heuristic' | 'llm' | 'none'."""
    ...
```

---

## Telemetry

When `auto_enhance` is on, emit **both** the original and enhanced char counts:

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
| `src/text_enhancer.py` | New — heuristic + LLM strategies |
| `src/prompts/enhance_for_tts.txt` | New — LLM system prompt |
| `src/main_window.py` | Add toggle to toolbar; persist to `user.yaml` |
| `src/main.py` | Call `enhance()` before `engine.speak()` and before export |
| `src/telemetry.py` | Add `enhanced_chars`, `enhanced_bytes`, `enhance_strategy` fields |

---

## Open Questions / ADR Candidates

- **ADR-012**: Which local LLM for strategy B? (Qwen 0.5B vs Phi-3-mini vs tinyllama)
- Should the toggle be global or per-engine? (e.g., Dia already formats with `[S1]` tags — LLM rewrite would break that)
- Should heuristic rules be user-configurable (checkboxes in Preferences)?
- Should the enhanced text be shown in the editor so the user can see what changed?

---

## Acceptance Criteria

- [ ] `heuristic_enhance()` covered by `tests/test_text_enhancer.py` (one test per rule, at minimum)
- [ ] Toggle visible in toolbar; state survives restart
- [ ] `enhance()` called in `main.py` before `speak()` when toggle is on
- [ ] `enhance()` called in `audio_exporter.py` before synthesis when toggle is on
- [ ] Telemetry emits `enhanced_chars` only when `auto_enhance` is on
- [ ] LLM path is a stub that raises `NotImplementedError` until ADR-012 is resolved
- [ ] Dia engine receives pre-enhanced text but the heuristic must NOT strip `[S1]`/`[S2]` tags
