from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.application.use_cases.index_concept import IndexConcept

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebuildReport:
    indexed: int = 0
    pruned: list[str] = field(default_factory=list)
    """Concept ids whose rows were removed because the bundle no longer has
    them. Named individually rather than counted: a prune is a deletion, and
    an operator running a recovery command should see what it took away."""


class RebuildIndex:
    """Walks the whole bundle and re-indexes every concept, then **removes what
    the bundle no longer has**.

    The second half is the part that was missing. Every derived store here is
    keyed by concept id and written by walking the filesystem, so a concept
    whose file disappears without going through `delete` leaves its rows behind
    forever: `ClearBundle` iterates `ConceptRepositoryPort.list()`, so a file
    already gone is a file it never sees. The orphan is not inert — `links`
    rows feed `expand_neighbors`, so a deleted concept keeps bridging graph
    expansion between concepts that no longer relate through it.

    Re-indexing alone could never fix that: overwriting rows for files that
    exist says nothing about rows for files that do not. Reconciling both
    directions is what makes this the recovery command its name implies.
    """

    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        index_concept: IndexConcept,
        metadata_repository: MetadataRepositoryPort | None = None,
        vector_search: VectorSearchPort | None = None,
    ) -> None:
        self._concept_repository = concept_repository
        self._index_concept = index_concept
        self._metadata_repository = metadata_repository
        self._vector_search = vector_search

    def run(self) -> RebuildReport:
        on_disk = [concept_id for concept_id in self._concept_repository.list()]
        for concept_id in on_disk:
            self._index_concept.run(self._concept_repository.load(concept_id))

        return RebuildReport(indexed=len(on_disk), pruned=self._prune(on_disk))

    def _prune(self, on_disk: list) -> list[str]:
        """Rows whose concept is not in the bundle any more.

        Vectors are deleted too, and unconditionally: `VectorSearchPort.delete`
        is a no-op for an id it does not hold, and a concept whose type put it
        in `NON_CONTENT_TYPES` never had a vector to begin with — asking is
        more code than telling."""
        if self._metadata_repository is None:
            return []

        known = set(self._metadata_repository.list_ids())
        stale = sorted(known - {str(concept_id) for concept_id in on_disk})
        for concept_id in stale:
            logger.info("pruning %s — no longer in the bundle", concept_id)
            self._metadata_repository.delete(concept_id)
            if self._vector_search is not None:
                self._vector_search.delete(concept_id)
        return stale
