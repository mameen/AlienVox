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


def test_strips_trailing_whitespace_per_line():
    result = heuristic_enhance("hello   \nworld")
    assert "hello\n" in result or result.startswith("hello\n")
    assert "   " not in result


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
