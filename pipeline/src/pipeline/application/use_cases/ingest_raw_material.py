"""Drives every unprocessed vault/raw/ item through the KnowledgeAgent, then applies
its create/merge decisions to the bundle and indexes whatever changed. Also
writes reciprocal relatedness backlinks into existing concepts a new concept
was judged related to (see `_write_reciprocal_backlinks`), and — for concepts
derived from a parsed source document — stamps §5.1 `sources[]` provenance
back at that document's `references/` hub and updates the hub's own
"## Derived concepts" list (see `_update_source_hub`)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from pipeline.application.ports.bundle_log import BundleLogPort
from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.raw_material_repository import (
    RawMaterialRepositoryPort,
)
from pipeline.application.use_cases.category_materializer import CategoryMaterializer
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.domain.agent import CreateDecision, MergeDecision, RejectDecision, RelatedConcept
from pipeline.domain.concept import Concept, ConceptId, Frontmatter, Source
from pipeline.domain.linking import add_link_section, add_related_links, insert_before_related
from pipeline.domain.slug import slugify

_DERIVED_CONCEPTS_HEADING = "## Derived concepts"

logger = logging.getLogger(__name__)


def _add_source(frontmatter: Frontmatter, source_concept_id: str) -> Frontmatter:
    """Adds a §5.1 `sources[]` entry pointing at the given reference-hub
    concept, deduped by resource — a concept can merge several chunks from
    the same source, and must not accumulate duplicate identical entries."""
    resource = f"/{source_concept_id}.md"
    if any(s.resource == resource for s in frontmatter.sources):
        return frontmatter
    return replace(frontmatter, sources=[*frontmatter.sources, Source(resource=resource)])


@dataclass(frozen=True)
class IngestOutcome:
    raw_id: str
    created: list[ConceptId] = field(default_factory=list)
    merged_into: list[ConceptId] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    errored: str | None = None
    """Set when an unexpected exception interrupted this item (Ollama down,
    an unparsable skill response, ...) rather than a considered rejection.
    The item is left retryable via `pipeline retry <item-id>` and every other
    item in the batch still gets processed — see `run()`."""


class IngestRawMaterial:
    def __init__(
        self,
        raw_material_repository: RawMaterialRepositoryPort,
        knowledge_agent: KnowledgeAgent,
        concept_repository: ConceptRepositoryPort,
        index_concept: IndexConcept,
        bundle_log: BundleLogPort,
    ) -> None:
        self._raw_material_repository = raw_material_repository
        self._knowledge_agent = knowledge_agent
        self._concept_repository = concept_repository
        self._index_concept = index_concept
        self._bundle_log = bundle_log
        self._category_materializer = CategoryMaterializer(
            concept_repository, index_concept, bundle_log
        )

    def run(self) -> list[IngestOutcome]:
        unprocessed = self._raw_material_repository.list_unprocessed()
        logger.info("ingest: %d unprocessed item(s)", len(unprocessed))
        outcomes: list[IngestOutcome] = []
        for raw in unprocessed:
            try:
                outcome = self._ingest_one(raw)
            except Exception as exc:  # noqa: BLE001 - isolate one bad item, keep the batch going
                logger.exception("ingest: raw/%s failed unexpectedly, marking as error", raw.id)
                self._raw_material_repository.mark_error(raw.id, str(exc))
                outcomes.append(IngestOutcome(raw_id=raw.id, errored=str(exc)))
                continue

            outcomes.append(outcome)
            if outcome.rejected and not (outcome.created or outcome.merged_into):
                self._raw_material_repository.mark_rejected(
                    raw.id, "; ".join(outcome.rejected)
                )
            else:
                self._raw_material_repository.mark_processed(raw.id)
            logger.info(
                "ingest: raw/%s -> created=%d merged=%d rejected=%d",
                raw.id,
                len(outcome.created),
                len(outcome.merged_into),
                len(outcome.rejected),
            )
        return outcomes

    def _ingest_one(self, raw) -> IngestOutcome:
        agent_result = self._knowledge_agent.run(raw)
        source_concept_id = (
            self._raw_material_repository.find_source_concept(raw.source_id)
            if raw.source_id
            else None
        )

        created: list[ConceptId] = []
        merged_into: list[ConceptId] = []
        rejected: list[str] = []

        for decision in agent_result.decisions:
            if isinstance(decision, CreateDecision):
                concept = self._materialize(decision)
                concept = self._category_materializer.link_new_categories(
                    concept, decision.new_categories, raw.id
                )
                if source_concept_id:
                    concept = replace(
                        concept, frontmatter=_add_source(concept.frontmatter, source_concept_id)
                    )
                self._concept_repository.save(concept)
                self._index_concept.run(concept)
                self._bundle_log.append(
                    action="create",
                    concept_id=str(concept.id),
                    raw_id=raw.id,
                    message=f"Added {concept.frontmatter.title or concept.id}, drafted from raw/{raw.id}.",
                )
                created.append(concept.id)
                self._raw_material_repository.link_concept(raw.id, str(concept.id))
                self._write_reciprocal_backlinks(concept, decision.related, raw.id)
                if source_concept_id:
                    self._update_source_hub(concept, source_concept_id, raw.id)
            elif isinstance(decision, MergeDecision):
                existing = self._concept_repository.load(decision.into)
                merged_frontmatter = (
                    _add_source(existing.frontmatter, source_concept_id)
                    if source_concept_id
                    else existing.frontmatter
                )
                merged = replace(
                    existing,
                    frontmatter=merged_frontmatter,
                    body=insert_before_related(existing.body, decision.addition),
                )
                self._concept_repository.save(merged)
                self._index_concept.run(merged)
                self._bundle_log.append(
                    action="merge",
                    concept_id=str(merged.id),
                    raw_id=raw.id,
                    message=f"Merged raw/{raw.id} into {merged.frontmatter.title or merged.id}.",
                )
                merged_into.append(decision.into)
                self._raw_material_repository.link_concept(raw.id, str(decision.into))
                if source_concept_id:
                    self._update_source_hub(merged, source_concept_id, raw.id)
            elif isinstance(decision, RejectDecision):
                self._bundle_log.append(
                    action="reject",
                    concept_id=None,
                    raw_id=raw.id,
                    message=decision.rationale,
                )
                rejected.append(decision.rationale)

        return IngestOutcome(
            raw_id=raw.id, created=created, merged_into=merged_into, rejected=rejected
        )

    def _write_reciprocal_backlinks(self, concept: Concept, related, raw_id: str) -> None:
        """A new concept's forward links to related concepts are already in
        its own body (KnowledgeAgent wove them in). This writes the reverse
        edge into each existing related concept's body too, bounded to the
        few candidates already judged related — the fix for relatedness
        otherwise being one-directional and order-dependent (an old concept
        could never gain a link to something genuinely related created after
        it)."""
        for link in related:
            existing = self._concept_repository.load(link.concept_id)
            back_link = replace(link, concept_id=concept.id, title=concept.frontmatter.title)
            new_body = add_related_links(existing.body, [back_link])
            if new_body == existing.body:
                continue  # already linked — dedup no-op

            updated = replace(existing, body=new_body)
            self._concept_repository.save(updated)
            self._index_concept.run(updated)
            self._bundle_log.append(
                action="relate",
                concept_id=str(updated.id),
                raw_id=raw_id,
                message=f"Linked back to {concept.frontmatter.title or concept.id} as related.",
            )

    def _update_source_hub(self, concept: Concept, source_concept_id: str, raw_id: str) -> None:
        """The concept's own `sources[]` (already stamped by the caller)
        points forward at the hub; this writes the reverse edge into the
        hub's own body, bounded to one hub per raw item — same shape as
        `_write_reciprocal_backlinks`, just for source-document provenance
        instead of semantic relatedness."""
        hub = self._concept_repository.load(ConceptId(source_concept_id))
        link = RelatedConcept(concept_id=concept.id, title=concept.frontmatter.title)
        new_body = add_link_section(hub.body, _DERIVED_CONCEPTS_HEADING, [link])
        if new_body == hub.body:
            return  # already listed — dedup no-op

        updated = replace(hub, body=new_body)
        self._concept_repository.save(updated)
        self._index_concept.run(updated)
        self._bundle_log.append(
            action="derive",
            concept_id=str(updated.id),
            raw_id=raw_id,
            message=f"Added {concept.frontmatter.title or concept.id} as derived from {hub.frontmatter.title or hub.id}.",
        )

    def _materialize(self, decision: CreateDecision) -> Concept:
        draft = decision.concept
        base = slugify(draft.frontmatter.title or draft.source_raw_id)
        concept_id = ConceptId(base)
        suffix = 2
        while self._concept_repository.exists(concept_id):
            concept_id = ConceptId(f"{base}-{suffix}")
            suffix += 1
        return Concept(id=concept_id, frontmatter=draft.frontmatter, body=draft.body)
