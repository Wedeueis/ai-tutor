from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import CandidateMatch


class VectorSearchPort(Protocol):
    """Upserts/queries/deletes concept embeddings by id."""

    def upsert(self, concept_id: str, vector: list[float], metadata: dict) -> None: ...

    def query(
        self, vector: list[float], k: int = 5, where: dict | None = None
    ) -> list[CandidateMatch]: ...

    def delete(self, concept_id: str) -> None: ...
