"""Reading a concept back against the text it was distilled from.

Two questions this answers, and they are the same query:

- *Is this concept faithful?* — show the passage and let a reader compare.
- *How did the author actually put it?* — show what surrounds the passage, so
  the claim is read in the argument it came from rather than as a fragment.

The second is why `context` exists at all. A distilled concept is a claim
lifted out of a discussion; handing it back with the sentences either side is
what turns checking into learning.
"""

from __future__ import annotations

from pipeline.application.ports.passage_reader import PassageReaderPort
from pipeline.domain.passage import Passage, RecalledPassage

DEFAULT_CONTEXT = 1
MAX_CONTEXT = 3
"""Neighbours per side. Capped because the caller is usually a local model with
a small window, and a passage buried in six others stops being context and
starts being the document."""

DEFAULT_LIMIT = 3
"""Passages per call when no specific citation is asked for. A concept merged
from many chunks would otherwise return the whole book."""

DEFAULT_CONTEXT_CHARS = 1200
"""How much neighbouring text to render per side. A budget, not a sentence
count: chunks vary from a heading to four thousand characters, so counting
passages would make the cost of `context=1` unpredictable."""


class RecallPassages:
    def __init__(
        self,
        passages: PassageReaderPort,
        context_chars: int = DEFAULT_CONTEXT_CHARS,
    ) -> None:
        self._passages = passages
        self._context_chars = context_chars

    def run(
        self,
        concept_id: str,
        source_id: str | None = None,
        context: int = DEFAULT_CONTEXT,
        limit: int = DEFAULT_LIMIT,
    ) -> list[RecalledPassage]:
        """`source_id` is a `sources[].id` from the concept's frontmatter — the
        same string a `[^footnote]` in its body carries. Asking for one is how
        a reader checks *this specific claim* rather than the concept at large;
        omitting it returns the first few passages that fed the concept."""
        found = self._passages.for_concept(concept_id)
        if source_id is not None:
            found = [passage for passage in found if passage.source_id == source_id]
        else:
            found = found[: max(limit, 0)]

        radius = min(max(context, 0), MAX_CONTEXT)
        return [self._recall(passage, radius) for passage in found]

    def _recall(self, passage: Passage, radius: int) -> RecalledPassage:
        if radius == 0:
            return RecalledPassage(passage=passage)

        neighbours = self._passages.neighbours(passage.id, radius)
        ordinal = passage.ordinal
        before = [n for n in neighbours if ordinal is not None and _before(n, ordinal)]
        after = [n for n in neighbours if ordinal is not None and not _before(n, ordinal)]
        return RecalledPassage(
            passage=passage,
            # Truncated from the *inside out*: the text nearest the passage is
            # the text that explains it, so `before` keeps its tail and `after`
            # keeps its head.
            before=_tail(_join(before), self._context_chars),
            after=_head(_join(after), self._context_chars),
        )


def _before(passage: Passage, ordinal: int) -> bool:
    return passage.ordinal is not None and passage.ordinal < ordinal


def _join(passages: list[Passage]) -> str | None:
    return "\n\n".join(passage.text for passage in passages) or None


def _tail(text: str | None, budget: int) -> str | None:
    if text is None or len(text) <= budget:
        return text
    return f"…{text[-budget:]}"


def _head(text: str | None, budget: int) -> str | None:
    if text is None or len(text) <= budget:
        return text
    return f"{text[:budget]}…"
