from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import CandidateMatch, DraftConcept
from pipeline.domain.relevance import RelevanceEvidence


class RelevanceEvidencePort(Protocol):
    """Gathers what `judge_relevance` needs to decide fit to the bundle.

    Split from the decision for the reason issue #7 gives: redundancy needs
    embeddings and a search over the whole bundle, which are adapter concerns,
    while the thresholds and the accept/reject rollup are plain domain logic
    that must stay testable without either.

    Not an LLM skill. Fit is a measurable property of the bundle, and asking a
    model to re-judge what a vector search already answered would add cost,
    latency and variance for nothing."""

    def gather(
        self,
        draft: DraftConcept,
        candidates: list[CandidateMatch],
        source_id: str | None = None,
    ) -> RelevanceEvidence:
        """`candidates` are the draft-match search results the caller already
        has — passed in rather than re-searched, so the gate costs no extra
        embedding or query.

        `source_id` is the raw item's source document, when it had one. The
        draft cannot carry its own provenance yet: `sources[]` is stamped after
        the agent runs."""
        ...
