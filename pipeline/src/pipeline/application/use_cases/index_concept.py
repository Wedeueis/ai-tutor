from __future__ import annotations

from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.application.use_cases.ensure_index_fingerprint import (
    EnsureIndexFingerprint,
)
from pipeline.domain.concept import NON_CONTENT_TYPES, Concept


class IndexConcept:
    """Embeds a concept's body and upserts it into both the vector store (semantic
    search) and the metadata store (structured queries)."""

    def __init__(
        self,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        metadata_repository: MetadataRepositoryPort,
        fingerprint: EnsureIndexFingerprint | None = None,
    ) -> None:
        self._embedding = embedding
        self._vector_search = vector_search
        self._metadata_repository = metadata_repository
        self._fingerprint = fingerprint

    def run(self, concept: Concept) -> None:
        if concept.frontmatter.type not in NON_CONTENT_TYPES:
            # Before the embed, not after: the point is to refuse to *add* a
            # vector from a different model to an existing collection.
            if self._fingerprint is not None:
                self._fingerprint.check()
            vector = self._embedding.embed_document(concept.body)
            if self._fingerprint is not None:
                self._fingerprint.record(vector)
            metadata = {"type": concept.frontmatter.type}
            if concept.frontmatter.domain is not None:
                metadata["domain"] = concept.frontmatter.domain
            self._vector_search.upsert(str(concept.id), vector, metadata=metadata)
        self._metadata_repository.upsert(concept)
