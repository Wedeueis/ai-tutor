"""Getting JSON out of a small local model's prose.

Extracted from `assessment.py`, which paid for this once already. Every
LLM-backed adapter here asks for JSON and gets it wrapped in something: a
```json fence, a sentence of preamble, or leaked reasoning ahead of the answer
(#12). A second adapter re-deriving that tolerance would drift from the first,
and the two would fail on different malformed outputs.

Deliberately not a `JsonSkillPort`: this is not a seam anything swaps, it is
the parsing every adapter on this side of the port does before it can honour
its own contract.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def as_object(raw: str) -> dict[str, Any]:
    parsed = parse(raw)
    return parsed if isinstance(parsed, dict) else {}


def as_array(raw: str) -> list[Any]:
    parsed = parse(raw)
    if isinstance(parsed, list):
        return parsed
    # A model returning exactly one item sometimes returns the bare object.
    return [parsed] if isinstance(parsed, dict) else []


def parse(raw: str) -> Any:
    """Tolerant extraction: fenced first, then bare, then the widest
    brace/bracket span in the text. Returns `None` rather than raising — every
    caller here has a defined answer for "the model said nothing usable", and
    that answer is never a traceback."""
    text = raw.strip()
    fenced = _JSON_BLOCK.search(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    end = max(text.rfind("}"), text.rfind("]"))
    if start == -1 or end <= start:
        logger.warning("no JSON found in model output")
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("model output was not parseable JSON")
        return None
