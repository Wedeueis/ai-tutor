"""Cheap, deterministic (no LLM) check for text that isn't real prose — e.g.
a Docling table parse gone wrong. Pure, no I/O.

This only catches *raw*, undressed garbage — a chunk before any LLM has had
a chance to wrap it in grammatical sentences (see parse_source_documents.py).
It is deliberately not used to judge whether an already-extracted concept is
low quality: a vacuous-but-grammatical fragment ("The following table
represents a collection of data points...") looks lexically identical to
good prose, which needs actual understanding to catch — see
QualityAuditSkillPort / `pipeline audit` instead."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z]{3,}")

MIN_TOKENS_TO_JUDGE = 5
MIN_WORD_TOKEN_RATIO = 0.15


def looks_like_garbled_table(text: str) -> bool:
    """True when real words (3+ letters) are a tiny fraction of the
    whitespace-split tokens — what a mangled markdown table dump looks like
    (`| 4 | 8 | 5.19 |...`), never what real prose looks like. Too-short
    text is inconclusive, not flagged."""
    tokens = text.split()
    if len(tokens) < MIN_TOKENS_TO_JUDGE:
        return False
    word_ratio = len(_WORD_RE.findall(text)) / len(tokens)
    return word_ratio < MIN_WORD_TOKEN_RATIO
