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
  - llm_enhance: on-device model rewrite (ADR-012: Qwen2.5-0.5B-Instruct
    GGUF via llama-cpp-python — smallest of the candidates considered,
    in-process per SKILL.md §3's no-subprocess rule). Lazy-loaded on
    first use; the ~470MB weight file downloads to .models/text_enhancer/
    on first call and is cached after.

Dia's [S1]/[S2] speaker tags must survive both strategies untouched —
they aren't prosody punctuation, they're semantic markers the engine
parses. heuristic_enhance() stashes/restores them structurally;
llm_enhance() instructs the model to preserve them via the system prompt
and then validates the tag count didn't change, raising if it did (the
caller — AppController._enhance_text — falls back to heuristic_enhance
on any exception from here, never to raw unenhanced text).
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

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


# ── LLM strategy (ADR-012: Qwen2.5-0.5B-Instruct GGUF) ─────────────────────

_GGUF_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
_GGUF_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"

_DEFAULT_PROMPT_PATH = Path(__file__).parent.parent / "resources" / "prompts" / "enhance_for_tts.txt"
_FALLBACK_SYSTEM_PROMPT = (
    "You rewrite text so it sounds natural when read aloud by a text-to-speech engine. "
    "Fix awkward phrasing and missing punctuation for natural pacing. Do not change the "
    "meaning or add commentary — output ONLY the rewritten text."
)

_llm_lock = threading.Lock()
_llm_instance: Any = None  # lazily-loaded llama_cpp.Llama singleton


def _get_llm() -> Any:
    """Lazily loads (and caches) the GGUF model, downloading it on first
    use. Guarded by a lock since speak() calls can arrive from different
    threads (hotkey vs. UI button)."""
    global _llm_instance
    with _llm_lock:
        if _llm_instance is None:
            from huggingface_hub import hf_hub_download
            from llama_cpp import Llama

            from ..config import models_root

            model_dir = models_root() / "text_enhancer"
            model_dir.mkdir(parents=True, exist_ok=True)
            model_path = hf_hub_download(
                repo_id=_GGUF_REPO, filename=_GGUF_FILENAME, local_dir=str(model_dir),
            )
            _llm_instance = Llama(model_path=model_path, n_ctx=2048, verbose=False)
        return _llm_instance


def llm_enhance(text: str, prompt_path: "Path | str | None" = None) -> str:
    """LLM rewrite for natural speech (ADR-012: Qwen2.5-0.5B-Instruct).

    Raises on any failure (model load, generation, or output validation)
    — the caller (AppController._enhance_text) falls back to
    heuristic_enhance rather than propagating the failure or returning
    unenhanced text."""
    if not text:
        return text

    path = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_PATH
    system_prompt = path.read_text(encoding="utf-8") if path.exists() else _FALLBACK_SYSTEM_PROMPT

    llm = _get_llm()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        max_tokens=max(64, int(len(text.split()) * 2.5) + 32),
        temperature=0.2,
    )
    result = response["choices"][0]["message"]["content"].strip()

    if not result:
        raise RuntimeError("llm_enhance: model returned empty output")
    if len(_SPEAKER_TAG_RE.findall(result)) != len(_SPEAKER_TAG_RE.findall(text)):
        raise RuntimeError("llm_enhance: speaker tag count changed — discarding output")
    if len(result) > len(text) * 3 or len(result) < len(text) * 0.3:
        raise RuntimeError(
            f"llm_enhance: implausible output length ({len(text)} -> {len(result)} chars)"
        )
    return result


def enhance(text: str, strategy: str = "none") -> str:
    """Entry point. strategy: 'none' | 'heuristic' | 'llm'."""
    if strategy == "none":
        return text
    if strategy == "llm":
        return llm_enhance(text)
    if strategy == "heuristic":
        return heuristic_enhance(text)
    raise ValueError(f"unknown enhance strategy {strategy!r}")
