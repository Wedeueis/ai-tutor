from __future__ import annotations

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.use_cases.index_concept import IndexConcept


class RebuildIndex:
    """Walks the whole bundle and re-indexes every concept. Use after bulk edits or
    to recover from a stale/corrupted vector or metadata store."""

    def __init__(
        self, concept_repository: ConceptRepositoryPort, index_concept: IndexConcept
    ) -> None:
        self._concept_repository = concept_repository
        self._index_concept = index_concept

    def run(self) -> int:
        count = 0
        for concept_id in self._concept_repository.list():
            concept = self._concept_repository.load(concept_id)
            self._index_concept.run(concept)
            count += 1
        return count
