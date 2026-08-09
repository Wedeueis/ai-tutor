from __future__ import annotations

from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.domain.concept import Concept

# Structural/navigation types (curated link hubs, domain scaffolding) aren't
# ingestible content — they must never surface as an entity-disambiguation
# candidate a draft could get merged into. Still tracked in the metadata store
# (domain classification needs `find_ids_by_type("Domain")`), just excluded
# from semantic search/candidate matching.
_NON_CONTENT_TYPES = {"MOC", "Domain"}


class IndexConcept:
    """Embeds a concept's body and upserts it into both the vector store (semantic
    search) and the metadata store (structured queries)."""

    def __init__(
        self,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        metadata_repository: MetadataRepositoryPort,
    ) -> None:
        self._embedding = embedding
        self._vector_search = vector_search
        self._metadata_repository = metadata_repository

    def run(self, concept: Concept) -> None:
        if concept.frontmatter.type not in _NON_CONTENT_TYPES:
            vector = self._embedding.embed(concept.body)
            metadata = {"type": concept.frontmatter.type}
            if concept.frontmatter.domain is not None:
                metadata["domain"] = concept.frontmatter.domain
            self._vector_search.upsert(str(concept.id), vector, metadata=metadata)
        self._metadata_repository.upsert(concept)
