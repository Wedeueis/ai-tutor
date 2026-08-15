"""Pulling a JSON value out of a chat model's reply. Pure — no I/O.

Lives in the domain rather than in a client because it is provider-agnostic:
every model wraps JSON in prose or code fences sometimes, and both the local
and the cloud client need the identical, slightly fiddly parse. Duplicating it
per provider is how the two drift."""

from __future__ import annotations

import json
from typing import Any


class MalformedJsonResponse(ValueError):
    """The model replied, but not with JSON we can use. Distinct from a
    transport failure: retrying the same request will not fix it."""


def extract_json(text: str) -> dict[str, Any] | list[Any]:
    """The first complete JSON value in `text`.

    Chat models routinely wrap JSON in prose or code fences, and tack on
    commentary *after* the value. So this scans to the first `{`/`[` and
    decodes incrementally, rather than assuming the whole remainder is valid
    JSON or using a greedy brace-to-brace regex (which a nested object or a
    trailing sentence both defeat)."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        raise MalformedJsonResponse(f"no JSON found in response: {text!r}")

    body = text[start:]
    # strict=False: models routinely emit literal newlines inside JSON string
    # values (e.g. multi-line "body" fields) instead of \n.
    decoder = json.JSONDecoder(strict=False)
    try:
        value, _ = decoder.raw_decode(body)
    except json.JSONDecodeError as exc:
        repaired = _close_unterminated(body)
        if repaired is None:
            raise MalformedJsonResponse(f"invalid JSON in response: {exc}") from exc
        try:
            value, _ = decoder.raw_decode(repaired)
        except json.JSONDecodeError:
            raise MalformedJsonResponse(f"invalid JSON in response: {exc}") from exc
    return value


def _close_unterminated(body: str) -> str | None:
    """Appends the brackets a model forgot to close, or None if that isn't the
    problem.

    Cheap models emit a complete-looking sequence of objects and then simply
    omit the final `]` — observed from `deepseek-v4-flash` on the prerequisite
    prompt, with `finish_reason: stop`, so it is the model ending early rather
    than a token limit. Throwing away five perfectly good rubric scores over a
    missing character is worse than closing it.

    Deliberately narrow: it only ever *appends* closers for brackets that are
    still open outside a string. It cannot repair a truncated key, a broken
    value, or anything mid-token — those still raise, because guessing at them
    would invent content the model never produced."""
    depth: list[str] = []
    in_string = False
    escaped = False
    for char in body:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth.append("]" if char == "[" else "}")
        elif char in "]}":
            if not depth or depth[-1] != char:
                return None  # mismatched, not merely unfinished
            depth.pop()

    if in_string or not depth:
        return None
    # Drop a dangling comma or partial fragment after the last complete value.
    trimmed = body.rstrip()
    cut = max(trimmed.rfind("}"), trimmed.rfind("]"))
    if cut == -1:
        return None
    return trimmed[: cut + 1] + "".join(reversed(depth))


def extract_json_object(text: str) -> dict[str, Any]:
    """`extract_json` for the skills whose prompt asks for a single object —
    every one of them reads the result with `.get`, so an array coming back is
    a model failure like any other malformed response, raised here rather than
    handed on to become an `AttributeError` inside a skill adapter."""
    value = extract_json(text)
    if not isinstance(value, dict):
        raise MalformedJsonResponse(
            f"expected a JSON object, got {type(value).__name__}: {value!r}"
        )
    return value
