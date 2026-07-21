"""Text enhancement for more natural TTS delivery.

Rewrites raw editor text before it reaches an engine's synthesize/speak
call, fixing formatting artifacts that have no spoken equivalent
(excessive whitespace, doubled punctuation, unterminated sentences, ...).
See docs/issues/todo_004.md for the full design rationale.

Called from AppController._speak_locked (and, eventually, the export
path) — never by a View directly; the enhance_strategy toggle lives on
AppState like every other user-facing setting.

Two strategies:
  - heuristic_enhance: pure Python, zero dependencies, deterministic.
  - llm_enhance: on-device model rewrite — not yet implemented (ADR-012
    is still open on model selection); raises NotImplementedError so a
    caller accidentally selecting "llm" fails loudly instead of silently
    doing nothing.

Dia's [S1]/[S2] speaker tags must survive heuristic_enhance() untouched —
they aren't prosody punctuation, they're semantic markers the engine
parses.
"""
from __future__ import annotations

import re

_SPEAKER_TAG_RE = re.compile(r"\[S\d+\]")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_INLINE_SPACES_RE = re.compile(r"[ \t]{2,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_REPEATED_PUNCT_RE = re.compile(r"([!?])\1+")
_MIXED_REPEATED_PUNCT_RE = re.compile(r"[!?]{2,}")
_ELLIPSIS_RE = re.compile(r"\.{3,}")
_DASH_RE = re.compile(r"\s*[–—]\s*")
_LONE_SYMBOL_LINE_RE = re.compile(r"^[|\-~=_*^>#`\s]+$", re.MULTILINE)
_SENTENCE_END_RE = re.compile(r'[.!?…"\')\]]$')


def _protect_speaker_tags(text: str) -> tuple[str, list[str]]:
    """Swap [S1]/[S2]-style tags for placeholders so later rules can't
    touch them, returning the placeholder text and the tags to restore."""
    tags: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        tags.append(m.group(0))
        return f"\x00{len(tags) - 1}\x00"

    return _SPEAKER_TAG_RE.sub(_stash, text), tags


def _restore_speaker_tags(text: str, tags: list[str]) -> str:
    for i, tag in enumerate(tags):
        text = text.replace(f"\x00{i}\x00", tag)
    return text


def heuristic_enhance(text: str) -> str:
    """Fast rule-based whitespace/punctuation cleanup. Zero dependencies,
    deterministic — safe to run on every speak() call unconditionally
    once a caller opts in via AppState.enhance_strategy."""
    if not text:
        return text

    text, tags = _protect_speaker_tags(text)

    text = _LONE_SYMBOL_LINE_RE.sub("", text)
    text = _DASH_RE.sub(", ", text)
    text = _ELLIPSIS_RE.sub("…", text)
    text = _REPEATED_PUNCT_RE.sub(r"\1", text)
    text = _MIXED_REPEATED_PUNCT_RE.sub(lambda m: m.group(0)[0], text)
    text = _INLINE_SPACES_RE.sub(" ", text)
    text = _TRAILING_WS_RE.sub("", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)

    paragraphs = [p for p in text.split("\n\n")]
    fixed_paragraphs = []
    for p in paragraphs:
        stripped = p.rstrip()
        if stripped and not _SENTENCE_END_RE.search(stripped):
            stripped += "."
        fixed_paragraphs.append(stripped)
    text = "\n\n".join(fixed_paragraphs)

    text = text.strip("\n")
    text = _restore_speaker_tags(text, tags)
    return text


def llm_enhance(text: str, prompt_path: "str | None" = None) -> str:
    """LLM rewrite for natural speech. Raises NotImplementedError until
    ADR-012 selects a model — see docs/issues/todo_004.md."""
    raise NotImplementedError("LLM enhancer pending ADR-012 model selection")


def enhance(text: str, strategy: str = "none") -> str:
    """Entry point. strategy: 'none' | 'heuristic' | 'llm'."""
    if strategy == "none":
        return text
    if strategy == "llm":
        return llm_enhance(text)
    if strategy == "heuristic":
        return heuristic_enhance(text)
    raise ValueError(f"unknown enhance strategy {strategy!r}")
