"""Value objects produced by the knowledge agent's LLM-backed skills. These are pure
data — the reasoning that produces them lives behind ports/adapters, not here."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.domain.concept import ConceptId, Frontmatter


@dataclass(frozen=True)
class DraftConcept:
    """One candidate concept produced by the extraction skill from a raw item."""

    frontmatter: Frontmatter
    body: str
    source_raw_id: str


@dataclass(frozen=True)
class CandidateMatch:
    """One existing concept surfaced as a possible match for a draft, with its
    similarity score from vector search."""

    concept_id: ConceptId
    score: float


@dataclass(frozen=True)
class DisambiguationVerdict:
    """Same-entity resolution: is this draft the same concept as an existing one?"""

    same_as: ConceptId | None
    confidence: float
    rationale: str = ""


@dataclass(frozen=True)
class TypeClassificationVerdict:
    """Which `type` a draft concept belongs to, resolved against the vocabulary of
    types already in use in the vault (scoped to a domain, when one is known)."""

    resolved_type: str
    is_new_type: bool
    rationale: str = ""


@dataclass(frozen=True)
class DomainCandidate:
    """One existing `type: Domain` concept, offered to the domain-classification
    skill as a thing a draft might belong to."""

    concept_id: ConceptId
    title: str | None
    description: str | None


@dataclass(frozen=True)
class DomainClassificationVerdict:
    """Which existing Domain a draft belongs to, if any. `domain` is None when
    confidence is too low — the draft is still created, but left for human triage
    rather than force-fit into a domain or auto-minting a new one."""

    domain: ConceptId | None
    confidence: float
    rationale: str = ""


@dataclass(frozen=True)
class RelatednessCandidate:
    """One existing concept, not judged the same entity as the draft, offered
    to the relatedness skill as something the draft might still be worth
    linking to."""

    concept_id: ConceptId
    title: str | None
    score: float


@dataclass(frozen=True)
class RelatedConcept:
    """One existing concept the relatedness skill judged genuinely related to
    a draft — becomes a §6 link in the draft's body, not a merge."""

    concept_id: ConceptId
    title: str | None
    reason: str = ""


@dataclass(frozen=True)
class RelatednessVerdict:
    """Which of the offered candidates, if any, are genuinely related to the
    draft. Empty when nothing is related enough to link."""

    related: list[RelatedConcept] = field(default_factory=list)


@dataclass(frozen=True)
class QualityAuditVerdict:
    """Whether an already-published concept stands alone as genuinely useful
    knowledge, judged directly against its own body — no raw source needed,
    since this audits existing vault content rather than a fresh draft. Used
    by AuditConceptQuality (`pipeline audit`), not KnowledgeAgent."""

    standalone_quality: bool
    reason: str = ""


@dataclass(frozen=True)
class CreateDecision:
    """A brand-new draft to write. Quality-eval failure never blocks this — it
    only withholds `domain` (see knowledge_agent.py) — so this decision always
    means the concept gets created."""

    concept: DraftConcept
    related: list[RelatedConcept] = field(default_factory=list)
    """Existing concepts judged related (already woven into `concept.body` as
    forward links) — carried here too so IngestRawMaterial can also write a
    reciprocal backlink into each existing concept's own body, keeping
    relatedness from being one-directional and order-dependent."""


@dataclass(frozen=True)
class MergeDecision:
    into: ConceptId
    addition: str


@dataclass(frozen=True)
class RejectDecision:
    """A merge addition that failed its quality eval and was therefore NOT
    applied to the existing target concept. Scoped to merges only — brand-new
    drafts are never rejected outright, see CreateDecision."""

    source_raw_id: str
    rationale: str


@dataclass(frozen=True)
class AgentResult:
    """The KnowledgeAgent's decisions for one raw item — zero or more drafts, each
    resolved to create, merge into an existing concept, or (merge-only) reject."""

    decisions: list[CreateDecision | MergeDecision | RejectDecision] = field(
        default_factory=list
    )
