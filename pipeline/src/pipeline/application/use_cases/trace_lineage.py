from __future__ import annotations

from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.domain.concept import TypedLink

DEFAULT_MAX_HOPS = 3


class TraceLineage:
    """As thin as `SearchConcepts`: delegates straight to
    `MetadataRepositoryPort.trace_lineage` — every typed-relation path up to
    `max_hops` hops from a concept, e.g. to answer "was this decision
    superseded?" by walking `supersedes`/`superseded_by` edges."""

    def __init__(self, metadata_repository: MetadataRepositoryPort) -> None:
        self._metadata_repository = metadata_repository

    def run(
        self,
        concept_id: str,
        relation_type: str | None = None,
        direction: str = "both",
        max_hops: int = DEFAULT_MAX_HOPS,
    ) -> list[list[TypedLink]]:
        return self._metadata_repository.trace_lineage(
            concept_id, relation_type, direction, max_hops
        )
