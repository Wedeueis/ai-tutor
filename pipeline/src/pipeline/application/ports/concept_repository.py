from __future__ import annotations

from typing import Protocol

from pipeline.domain.concept import Concept, ConceptId


class ConceptRepositoryPort(Protocol):
    """Reads and writes concept documents in the bundle."""

    def load(self, concept_id: ConceptId) -> Concept: ...

    def save(self, concept: Concept) -> None: ...

    def list(self) -> list[ConceptId]: ...

    def exists(self, concept_id: ConceptId) -> bool: ...

    def delete(self, concept_id: ConceptId) -> None: ...
