"""Does this draft belong in *this* bundle?

**Relevance is extrinsic, and that is the whole point.** The `evals/` rubrics
judge a draft on its own — traceable, substantial, accurately titled — which a
well-written note about something completely off-topic passes easily. Fit to
the bundle cannot be judged without the rest of the bundle, so no intrinsic
rubric can express it (issue #7).

Two ways a draft fails to fit:

- **Redundant** — the bundle already covers this. Distinct from a merge: the
  disambiguation skill decides "the same entity" and merges; this catches the
  near-duplicate it declined to merge.
- **Off-topic** — unrelated to anything the bundle is about.

Pure domain. Thresholds, how signals combine, and the accept/reject rollup live
here, in the same shape as `aggregate_scores`; gathering the evidence needs
embeddings and a search over the bundle, which is a port
(`RelevanceEvidencePort`).

**The score is never persisted.** It informs one decision at ingest and is then
discarded — §5.1 refuses to store a credibility number precisely because it
starts going stale the moment it is written."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REDUNDANCY_THRESHOLD = 0.95
"""How similar to an existing concept before the draft adds nothing.

Deliberately high. Disambiguation already merges at 0.75 confidence when it
judges two things the *same entity*; anything this gate rejects is a draft that
was explicitly judged a different entity, so the bar for overriding that has to
be near-identity."""

DEFAULT_TOPICALITY_FLOOR = 0.15
"""How unrelated to everything before the draft is off-topic.

Deliberately low. A vault is meant to grow into new subjects, and rejecting a
genuinely new topic is a worse failure than admitting a marginal one — the
audit and quality gates get another look, but a rejected draft is simply gone."""

MIN_BUNDLE_FOR_TOPICALITY = 10
"""Below this, no draft is off-topic.

A bundle of three concepts has not established what it is about, so "unrelated
to everything here" says nothing yet. Without this floor, the gate would reject
the fourth concept of a new vault for not resembling the first three."""

CREDIBILITY_MARGIN = 0.05
"""How much benefit of the doubt a source with known signals earns on the
topicality floor.

Signals can only ever *help*. Absent signals leave the floor exactly where it
is, because most existing concepts and every hand-dropped note have none — a
gate that read absent as low-credibility would reject the entire existing
corpus and most future human input (ADR 0001)."""


@dataclass(frozen=True)
class RelevanceEvidence:
    """Everything the decision needs, already gathered.

    Note what is absent: the draft's *origin*. Material the tutor wrote into
    the inbox is scored exactly like a hand-dropped note (issue #7) — where a
    draft came from says nothing about whether it belongs."""

    bundle_size: int
    nearest_similarity: float | None = None
    """Similarity to the closest existing concept. None when the bundle is
    empty or the search found nothing — unknown, not zero."""
    nearest_concept_id: str | None = None
    has_credibility_signals: bool = False
    """Whether the draft's source declared an author or a modification date
    (§5.1). Never *which* — the curator infers from presence, and a score is
    neither computed from them nor stored."""


@dataclass(frozen=True)
class RelevanceVerdict:
    accepted: bool
    reason: str
    score: float
    """Carried for the bundle-log message and discarded with the verdict.
    Nothing may write this to frontmatter — see the module docstring."""


def judge_relevance(
    evidence: RelevanceEvidence,
    redundancy_threshold: float = DEFAULT_REDUNDANCY_THRESHOLD,
    topicality_floor: float = DEFAULT_TOPICALITY_FLOOR,
) -> RelevanceVerdict:
    """Accept unless the draft is redundant or off-topic.

    Accepting is the default, and every uncertainty resolves that way: an
    unknown similarity, a young bundle, an unrecognised source. Rejecting is
    the destructive branch — the draft is dropped and only the rationale
    survives in the bundle log — so it fires only on positive evidence."""
    similarity = evidence.nearest_similarity

    if similarity is None:
        return RelevanceVerdict(
            accepted=True,
            reason="nothing to compare against; relevance unknown, which is not a reason to reject",
            score=0.0,
        )

    if similarity >= redundancy_threshold:
        return RelevanceVerdict(
            accepted=False,
            reason=(
                f"already covered by {evidence.nearest_concept_id} "
                f"(similarity {similarity:.2f} >= {redundancy_threshold:.2f})"
            ),
            score=similarity,
        )

    if evidence.bundle_size < MIN_BUNDLE_FOR_TOPICALITY:
        return RelevanceVerdict(
            accepted=True,
            reason=(
                f"bundle of {evidence.bundle_size} has not established a topic yet; "
                "nothing can be off-topic from it"
            ),
            score=similarity,
        )

    floor = topicality_floor
    if evidence.has_credibility_signals:
        floor = max(0.0, floor - CREDIBILITY_MARGIN)

    if similarity < floor:
        return RelevanceVerdict(
            accepted=False,
            reason=(
                f"unrelated to anything in the bundle "
                f"(nearest {similarity:.2f} < {floor:.2f})"
            ),
            score=similarity,
        )

    return RelevanceVerdict(accepted=True, reason="fits the bundle", score=similarity)
