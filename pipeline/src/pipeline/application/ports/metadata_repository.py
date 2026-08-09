from __future__ import annotations

from typing import Protocol

from pipeline.domain.concept import Concept


class MetadataRepositoryPort(Protocol):
    """Structured queries over concept metadata (type, tags, status, links, ...)
    that don't need a semantic/vector search."""

    def upsert(self, concept: Concept) -> None: ...

    def list_distinct_types(self, domain: str | None = None) -> list[str]: ...

    def find_ids_by_type(self, concept_type: str) -> list[str]: ...

    def delete(self, concept_id: str) -> None: ...
