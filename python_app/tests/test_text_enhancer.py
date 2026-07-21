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


def test_llm_enhance_raises_not_implemented():
    """ADR-012 (model selection) is still open — a caller that reaches
    this path must fail loudly, not silently return unenhanced text."""
    with pytest.raises(NotImplementedError):
        llm_enhance("foo")
