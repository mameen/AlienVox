"""Tests for text_enhancer.heuristic_enhance — one test per rule minimum,
per docs/issues/todo_004.md's acceptance criteria.

Pure string transforms, no mocking needed — real function, real inputs.
"""
from __future__ import annotations

import pytest

from src.control.text_enhancer import enhance, heuristic_enhance, llm_enhance


def test_collapses_three_or_more_blank_lines():
    assert heuristic_enhance("a\n\n\n\nb") == "a.\n\nb."


def test_collapses_inline_double_spaces():
    assert heuristic_enhance("foo  bar") == "foo bar."


def test_reflows_single_newline_mid_sentence():
    """Word-wrapped text (pasted from a book/PDF, lines wrapped at
    ~70-80 chars) has a single newline in the middle of a sentence —
    that must become a space, not survive as a mid-sentence pause.
    Regression test: real user-reported bug, reproduced with the exact
    text that triggered it (opening lines of Alice in Wonderland)."""
    alice = (
        "Alice was beginning to get very tired of sitting by her sister on the\n"
        "bank, and of having nothing to do: once or twice she had peeped into\n"
        "the book her sister was reading, but it had no pictures or"
    )
    result = heuristic_enhance(alice)
    assert "\n" not in result
    assert "the bank" in result
    assert "into\nthe" not in result
    assert "into the" in result


def test_double_newline_paragraph_break_is_preserved_not_reflowed():
    """A blank line (intentional paragraph break) must stay a break —
    only single mid-sentence newlines get reflowed into spaces."""
    text = "First paragraph here.\n\nSecond paragraph here."
    result = heuristic_enhance(text)
    assert result == "First paragraph here.\n\nSecond paragraph here."


def test_markdown_link_becomes_link_text():
    """A raw markdown link read aloud is 'bracket ... bracket paren h
    t t p s colon slash slash...' — keep only the link text."""
    text = "See [www.gutenberg.org](https://www.gutenberg.org) for details."
    result = heuristic_enhance(text)
    assert result == "See www.gutenberg.org for details."
    assert "https" not in result
    assert "(" not in result and ")" not in result


def test_underscore_italic_span_is_unwrapped():
    text = "There was nothing so _very_ remarkable in that."
    assert heuristic_enhance(text) == "There was nothing so very remarkable in that."


def test_underscore_italic_span_reflowed_across_line_wrap():
    """Regression: a multi-word italic span that happens to wrap across
    a pasted-document line break must still be unwrapped — the reflow
    step must run BEFORE the italic regex, not after."""
    text = (
        "when the Rabbit actually _took a\n"
        "watch out of its waistcoat-pocket_, and looked at it."
    )
    result = heuristic_enhance(text)
    assert "_" not in result
    assert "took a watch out of its waistcoat-pocket, and looked at it." in result


def test_underscore_italic_does_not_touch_snake_case():
    """Underscores inside an identifier (no surrounding whitespace/
    punctuation) are not markdown italics — must survive untouched."""
    text = "Set the snake_case_variable to a value."
    assert heuristic_enhance(text) == "Set the snake_case_variable to a value."


# Disabled by request (2026-07-21) — see the matching commented-out rule
# in text_enhancer.py. Hearing "[Illustration]" spoken is fine for now.
# def test_standalone_bracket_placeholder_line_is_removed():
#     text = "Some text here.\n\n[Illustration]\n\nMore text after."
#     result = heuristic_enhance(text)
#     assert "[Illustration]" not in result
#     assert result == "Some text here.\n\nMore text after."


def test_inline_bracket_citation_is_not_removed():
    """Only a WHOLE line consisting of just a bracketed tag is stripped
    — an inline citation mid-sentence is left alone."""
    text = "Release date: June 27, 2008 [eBook #11]"
    result = heuristic_enhance(text)
    assert "[eBook #11]" in result


def test_strips_trailing_whitespace_before_reflow():
    """Trailing spaces before a mid-sentence newline don't survive as
    extra spaces once the newline itself is reflowed away."""
    result = heuristic_enhance("hello   \nworld")
    assert result == "hello world."


def test_adds_terminal_punctuation_to_unterminated_paragraph():
    assert heuristic_enhance("Go now") == "Go now."


def test_does_not_double_up_terminal_punctuation():
    assert heuristic_enhance("Already done.") == "Already done."
    assert heuristic_enhance("Already done!") == "Already done!"
    assert heuristic_enhance("Already done?") == "Already done?"


def test_collapses_repeated_punctuation():
    assert heuristic_enhance("Really???") == "Really?"
    assert heuristic_enhance("Wow!!!") == "Wow!"


def test_normalises_ellipsis():
    result = heuristic_enhance("Well...")
    assert result == "Well…"


def test_dash_becomes_comma_pause():
    assert heuristic_enhance("cats – dogs") == "cats, dogs."
    assert heuristic_enhance("cats — dogs") == "cats, dogs."


def test_strips_lone_symbol_lines():
    result = heuristic_enhance("Row one\n\n| --- |\n\nRow two")
    assert "---" not in result
    assert "Row one." in result
    assert "Row two." in result


def test_trims_leading_and_trailing_blank_lines():
    assert heuristic_enhance("\n\nHello") == "Hello."
    assert heuristic_enhance("Hello\n\n\n") == "Hello."


def test_empty_text_returns_empty():
    assert heuristic_enhance("") == ""


def test_dia_speaker_tags_survive_untouched():
    """[S1]/[S2] are semantic markers the engine parses, not prosody
    punctuation — the enhancer must never touch them."""
    text = "[S1] Hello there.  [S2] Well... how are you???"
    result = heuristic_enhance(text)
    assert "[S1]" in result
    assert "[S2]" in result


def test_dia_tags_unaffected_by_surrounding_cleanup():
    text = "[S1] foo  bar\n\n\n\n[S2] baz"
    result = heuristic_enhance(text)
    assert result.count("[S1]") == 1
    assert result.count("[S2]") == 1


def test_enhance_entry_point_none_returns_raw_text():
    assert enhance("foo  bar", "none") == "foo  bar"


def test_enhance_entry_point_heuristic_matches_direct_call():
    assert enhance("foo  bar", "heuristic") == heuristic_enhance("foo  bar")


def test_enhance_entry_point_unknown_strategy_raises():
    with pytest.raises(ValueError):
        enhance("foo", "not-a-real-strategy")


class _FakeLlm:
    """Stands in for llama_cpp.Llama — returns a canned chat completion
    without loading any real model, so these tests run without network
    access or the ~470MB GGUF download."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.last_messages: list[dict] | None = None

    def create_chat_completion(self, messages, max_tokens, temperature):
        self.last_messages = messages
        return {"choices": [{"message": {"content": self.response_text}}]}


def test_llm_enhance_empty_text_short_circuits_without_loading_model(monkeypatch):
    import src.control.text_enhancer as te
    monkeypatch.setattr(te, "_get_llm", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    assert llm_enhance("") == ""


def test_llm_enhance_returns_model_output(monkeypatch):
    import src.control.text_enhancer as te
    fake = _FakeLlm("Hello, world. This sounds better now.")
    monkeypatch.setattr(te, "_get_llm", lambda: fake)

    result = llm_enhance("hello   world this sounds better now")

    assert result == "Hello, world. This sounds better now."
    assert fake.last_messages[0]["role"] == "system"
    assert fake.last_messages[1] == {"role": "user", "content": "hello   world this sounds better now"}


def test_llm_enhance_raises_on_empty_model_output(monkeypatch):
    import src.control.text_enhancer as te
    monkeypatch.setattr(te, "_get_llm", lambda: _FakeLlm("   "))
    with pytest.raises(RuntimeError, match="empty output"):
        llm_enhance("some real text here")


def test_llm_enhance_raises_when_speaker_tag_count_changes(monkeypatch):
    """Guards against the model silently dropping/duplicating [S1]/[S2]
    tags — AppController falls back to heuristic when this fires."""
    import src.control.text_enhancer as te
    monkeypatch.setattr(te, "_get_llm", lambda: _FakeLlm("[S1] Hello there, friend."))
    with pytest.raises(RuntimeError, match="speaker tag"):
        llm_enhance("[S1] Hello there. [S2] How are you?")


def test_llm_enhance_raises_on_implausible_output_length(monkeypatch):
    import src.control.text_enhancer as te
    monkeypatch.setattr(te, "_get_llm", lambda: _FakeLlm("Hi."))
    with pytest.raises(RuntimeError, match="implausible"):
        llm_enhance(
            "This is a much longer piece of text that the tiny fake model "
            "response below is nowhere near the length of, which should trip "
            "the length-sanity check meant to catch truncated or hallucinated output."
        )


def test_llm_enhance_uses_prompt_file_content_as_system_prompt(monkeypatch, tmp_path):
    import src.control.text_enhancer as te
    fake = _FakeLlm("Rewritten text.")
    monkeypatch.setattr(te, "_get_llm", lambda: fake)

    prompt_file = tmp_path / "custom_prompt.txt"
    prompt_file.write_text("CUSTOM SYSTEM PROMPT", encoding="utf-8")

    llm_enhance("original text", prompt_path=prompt_file)

    assert fake.last_messages[0]["content"] == "CUSTOM SYSTEM PROMPT"
