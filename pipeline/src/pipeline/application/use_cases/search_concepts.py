from __future__ import annotations

from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.domain.agent import CandidateMatch


class SearchConcepts:
    def __init__(self, embedding: EmbeddingPort, vector_search: VectorSearchPort) -> None:
        self._embedding = embedding
        self._vector_search = vector_search

    def run(self, query: str, k: int = 5) -> list[CandidateMatch]:
        vector = self._embedding.embed(query)
        return self._vector_search.query(vector, k=k)
