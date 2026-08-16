"""Value objects produced by the knowledge agent's LLM-backed skills. These are pure
data — the reasoning that produces them lives behind ports/adapters, not here."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.domain.concept import ConceptId, Frontmatter
from pipeline.domain.prerequisites import PrerequisiteEdge


@dataclass(frozen=True)
class DraftConcept:
    """One candidate concept produced by the extraction skill from a raw item."""

    frontmatter: Frontmatter
    body: str
    source_raw_id: str


@dataclass(frozen=True)
class CandidateMatch:
    """One existing concept surfaced as a possible match — from a draft-match
    search (vector-search cosine similarity) or from `SearchConcepts` (a fused
    rank-based score: reciprocal rank fusion across semantic/lexical results,
    or a hop-decayed graph-expansion score — not a single homogeneous 0-1
    cosine similarity)."""

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
class CategoryCandidate:
    """One existing `type: Category` concept under a draft's chosen domain,
    offered to the category-classification skill as something the draft
    might belong to."""

    concept_id: ConceptId
    title: str | None


@dataclass(frozen=True)
class CategoryClassificationVerdict:
    """Which existing Categories a draft belongs to (zero or more — a concept
    can belong to several), plus any category titles proposed as new (minted
    only when nothing existing plausibly fits, mirroring
    `TypeClassificationVerdict.is_new_type`)."""

    categories: list[ConceptId] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)
    confidence: float = 0.0
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
    new_categories: list[str] = field(default_factory=list)
    """Category titles the classification skill proposed as new (nothing
    existing fit) — carried here because `KnowledgeAgent` can't materialize
    concepts itself; `IngestRawMaterial` creates each one as a real
    `type: Category` concept and links `concept.body` to it. Existing-category
    assignments, by contrast, are already woven into `concept.body` as links
    by `KnowledgeAgent`, the same way `related` links are."""
    prerequisites: list[PrerequisiteEdge] = field(default_factory=list)
    """Prerequisite edges, already woven into `concept.body` as
    `requires::`/`may_require::` lines. Carried here only so IngestRawMaterial
    can record them in the bundle log — unlike `related`, these get **no**
    reciprocal backlink: "A requires B" is a claim about A, and writing the
    reverse would assert a dependency nobody judged."""


@dataclass(frozen=True)
class MergeDecision:
    into: ConceptId
    addition: str


@dataclass(frozen=True)
class RejectDecision:
    """A draft that was not written. Two causes, and they are different in kind:

    - **A merge addition that failed its quality eval** — not applied to the
      existing target concept, which is left as it was.
    - **A draft judged not to belong in this bundle** (RF1.6) — redundant with
      something already here, or off-topic. Note this is about *fit*, not
      quality: a well-written note about the wrong subject is rejected here
      and would have passed every intrinsic rubric.

    Quality alone still never rejects a brand-new draft — a failing eval only
    withholds `domain` (see CreateDecision)."""

    source_raw_id: str
    rationale: str


@dataclass(frozen=True)
class AgentResult:
    """The KnowledgeAgent's decisions for one raw item — zero or more drafts, each
    resolved to create, merge into an existing concept, or (merge-only) reject."""

    decisions: list[CreateDecision | MergeDecision | RejectDecision] = field(
        default_factory=list
    )
