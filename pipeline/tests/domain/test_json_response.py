"""Pulling JSON out of a chat reply — the parse both providers share."""

import pytest

from pipeline.domain.json_response import (
    MalformedJsonResponse,
    extract_json,
    extract_json_object,
)


def test_a_bare_object_is_returned_as_is():
    assert extract_json('{"score": 0.9}') == {"score": 0.9}


def test_json_wrapped_in_prose_is_found():
    text = 'Sure! Here is the result:\n\n{"score": 0.9}\n\nLet me know if you need more.'

    assert extract_json(text) == {"score": 0.9}


def test_json_in_a_code_fence_is_found():
    assert extract_json('```json\n{"score": 0.9}\n```') == {"score": 0.9}


def test_commentary_after_the_value_does_not_break_the_parse():
    """A greedy brace-to-brace match would swallow the trailing sentence."""
    assert extract_json('{"a": 1} — and that is my reasoning. {not json}') == {"a": 1}


def test_a_nested_object_is_not_truncated():
    """The other way a greedy match fails: stopping at the first `}`."""
    text = '{"outer": {"inner": 1}, "after": 2}'

    assert extract_json(text) == {"outer": {"inner": 1}, "after": 2}


def test_an_array_is_returned_when_the_prompt_asked_for_one():
    assert extract_json('[{"rubric_id": "a"}, {"rubric_id": "b"}]') == [
        {"rubric_id": "a"},
        {"rubric_id": "b"},
    ]


def test_literal_newlines_inside_a_string_value_are_tolerated():
    """Models routinely emit a real newline inside a multi-line "body" field
    instead of the escape sequence JSON requires."""
    assert extract_json('{"body": "line one\nline two"}') == {"body": "line one\nline two"}


def test_no_json_at_all_is_a_malformed_response():
    with pytest.raises(MalformedJsonResponse, match="no JSON found"):
        extract_json("I'm sorry, I can't help with that.")


def test_broken_json_is_a_malformed_response():
    with pytest.raises(MalformedJsonResponse, match="invalid JSON"):
        extract_json('{"score": }')


def test_an_empty_response_is_a_malformed_response():
    """What `qwen3.5:4b` returns for the prerequisite prompt, and what a cloud
    reasoning model returns when it spends its budget before answering."""
    with pytest.raises(MalformedJsonResponse, match="no JSON found"):
        extract_json("")


def test_an_array_where_an_object_was_asked_for_is_rejected():
    """Every object-shaped caller reads the result with `.get`, so handing an
    array on would surface as an `AttributeError` inside a skill adapter."""
    with pytest.raises(MalformedJsonResponse, match="expected a JSON object"):
        extract_json_object('[{"a": 1}]')


def test_extract_json_object_returns_the_object():
    assert extract_json_object('Here: {"a": 1}') == {"a": 1}


# --- recovering an unterminated value ------------------------------------


def test_an_array_missing_its_closing_bracket_is_recovered():
    """Observed from `deepseek-v4-flash` with `finish_reason: stop` — it emits
    five complete rubric objects and simply omits the final `]`. Throwing away
    five good scores over one missing character is the worse failure."""
    text = '[\n  {"rubric_id": "a", "score": 1.0},\n  {"rubric_id": "b", "score": 0.5}\n'

    assert extract_json(text) == [
        {"rubric_id": "a", "score": 1.0},
        {"rubric_id": "b", "score": 0.5},
    ]


def test_an_object_missing_its_closing_brace_is_recovered():
    assert extract_json('{"outer": {"inner": 1}') == {"outer": {"inner": 1}}


def test_a_dangling_comma_after_the_last_value_is_dropped():
    assert extract_json('[{"a": 1}, {"b": 2},') == [{"a": 1}, {"b": 2}]


def test_recovery_does_not_invent_a_truncated_value():
    """Only *closers* are appended. A value cut off mid-token would have to be
    guessed at, and a fabricated rubric score is worse than a failed call."""
    with pytest.raises(MalformedJsonResponse, match="invalid JSON"):
        extract_json('[{"rubric_id": "a", "score": 1.0}, {"rubric_id": "b", "sco')


def test_recovery_does_not_repair_a_truncated_string():
    with pytest.raises(MalformedJsonResponse, match="invalid JSON"):
        extract_json('[{"rationale": "it was cut off mid-sen')


def test_mismatched_brackets_are_not_treated_as_unfinished():
    with pytest.raises(MalformedJsonResponse, match="invalid JSON"):
        extract_json('[{"a": 1]}')


def test_a_bracket_inside_a_string_does_not_confuse_the_repair():
    text = '[{"rationale": "an array looks like [this]"}'

    assert extract_json(text) == [{"rationale": "an array looks like [this]"}]


def test_an_escaped_quote_inside_a_string_does_not_confuse_the_repair():
    text = '[{"rationale": "he said \\"yes\\" clearly"}'

    assert extract_json(text) == [{"rationale": 'he said "yes" clearly'}]
