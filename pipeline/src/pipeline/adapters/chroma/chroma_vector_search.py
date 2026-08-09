"""VectorSearchPort backed by a local, persistent ChromaDB collection."""

from __future__ import annotations

from pathlib import Path

import chromadb

from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import ConceptId

_COLLECTION_NAME = "concepts"


class ChromaVectorSearch:
    def __init__(self, persist_dir: Path) -> None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            _COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, concept_id: str, vector: list[float], metadata: dict) -> None:
        clean_metadata = {k: v for k, v in metadata.items() if v is not None} or {"_empty": True}
        self._collection.upsert(ids=[concept_id], embeddings=[vector], metadatas=[clean_metadata])

    def query(
        self, vector: list[float], k: int = 5, where: dict | None = None
    ) -> list[CandidateMatch]:
        if self._collection.count() == 0:
            return []
        result = self._collection.query(query_embeddings=[vector], n_results=k, where=where)
        ids = result.get("ids", [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            CandidateMatch(concept_id=ConceptId(cid), score=1.0 - distance)
            for cid, distance in zip(ids, distances, strict=True)
        ]

    def delete(self, concept_id: str) -> None:
        self._collection.delete(ids=[concept_id])
