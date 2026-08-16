"""`RelevanceEvidencePort` composed from ports the pipeline already has.

A shared collaborator rather than a use case — the same shape as
`CategoryMaterializer`: it has no command of its own, it assembles what
`judge_relevance` needs from the metadata index and the search results the
caller already holds."""

from __future__ import annotations

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.raw_material_repository import RawMaterialRepositoryPort
from pipeline.domain.agent import CandidateMatch, DraftConcept
from pipeline.domain.concept import NON_CONTENT_TYPES, ConceptId
from pipeline.domain.relevance import RelevanceEvidence


class RelevanceEvidenceGatherer:
    def __init__(
        self,
        metadata_repository: MetadataRepositoryPort,
        concept_repository: ConceptRepositoryPort,
        raw_material_repository: RawMaterialRepositoryPort,
    ) -> None:
        self._metadata_repository = metadata_repository
        self._concept_repository = concept_repository
        self._raw_material_repository = raw_material_repository

    def gather(
        self,
        draft: DraftConcept,
        candidates: list[CandidateMatch],
        source_id: str | None = None,
    ) -> RelevanceEvidence:
        nearest = candidates[0] if candidates else None
        return RelevanceEvidence(
            bundle_size=self._bundle_size(),
            nearest_similarity=nearest.score if nearest else None,
            nearest_concept_id=str(nearest.concept_id) if nearest else None,
            has_credibility_signals=self._has_signals(source_id),
        )

    def _bundle_size(self) -> int:
        """Content concepts only. Categories, MOCs, Domains and source-document
        hubs are scaffolding — counting them would let a bundle of six real
        concepts and six Categories clear the topicality floor while it still
        has nothing to be off-topic from.

        Counted from the metadata index rather than by loading each file: this
        runs once per draft, and a bundle of any size would otherwise make the
        gate the most expensive step in ingest."""
        structural = {
            concept_id
            for concept_type in NON_CONTENT_TYPES
            for concept_id in self._metadata_repository.find_ids_by_type(concept_type)
        }
        return sum(
            1 for concept_id in self._concept_repository.list()
            if str(concept_id) not in structural
        )

    def _has_signals(self, source_id: str | None) -> bool:
        """Whether the source document this draft came from declared an author
        or a modification date.

        Read from the `references/` hub, not from the draft: `sources[]` is
        stamped by `IngestRawMaterial` *after* the agent runs, so a draft never
        carries its own provenance at the moment it is judged. A hand-dropped
        note has no source document at all, which is simply unknown — and
        unknown is neutral, never low (ADR 0001)."""
        if source_id is None:
            return False
        hub_id = self._raw_material_repository.find_source_concept(source_id)
        if hub_id is None:
            return False
        hub = self._concept_repository.load(ConceptId(hub_id))
        # Presence only, never the values: the curator infers from the fact
        # that a source declared itself, and computes no score from a name.
        return any(s.author or s.last_modified for s in hub.frontmatter.sources)
