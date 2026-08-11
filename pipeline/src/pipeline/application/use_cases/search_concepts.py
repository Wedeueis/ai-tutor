from __future__ import annotations

from datetime import date

from pipeline.application.ports.embedding import EmbeddingPort
from pipeline.application.ports.metadata_repository import MetadataRepositoryPort
from pipeline.application.ports.vector_search import VectorSearchPort
from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import ConceptId
from pipeline.domain.search import DEFAULT_RRF_K, reciprocal_rank_fusion

DEFAULT_POOL_K = 20
DEFAULT_GRAPH_SEED_K = 5
DEFAULT_GRAPH_MAX_HOPS = 2
DEFAULT_GRAPH_DECAY = 0.5
DEFAULT_GRAPH_CATEGORY_DECAY = 0.85
DEFAULT_STRUCTURED_MIN_RESULTS = 3


class SearchConcepts:
    """Hybrid search: stage 0 answers a structured type/date query directly
    when one is given and it has enough hits ("ontology-first"); otherwise,
    stage 1 fuses semantic (vector) and lexical (FTS5) rankings via
    reciprocal rank fusion, and stage 2 expands from the fused ranking's top
    hits through the link graph (decayed by hop distance) and reranks the
    combined set. The returned `CandidateMatch.score` is a fused rank-based
    number (or `1.0` for a stage-0 structural match), not a single
    homogeneous 0-1 cosine similarity."""

    def __init__(
        self,
        embedding: EmbeddingPort,
        vector_search: VectorSearchPort,
        metadata_repository: MetadataRepositoryPort,
        pool_k: int = DEFAULT_POOL_K,
        graph_seed_k: int = DEFAULT_GRAPH_SEED_K,
        graph_max_hops: int = DEFAULT_GRAPH_MAX_HOPS,
        graph_decay: float = DEFAULT_GRAPH_DECAY,
        graph_category_decay: float = DEFAULT_GRAPH_CATEGORY_DECAY,
        rrf_k: int = DEFAULT_RRF_K,
        structured_min_results: int = DEFAULT_STRUCTURED_MIN_RESULTS,
    ) -> None:
        self._embedding = embedding
        self._vector_search = vector_search
        self._metadata_repository = metadata_repository
        self._pool_k = pool_k
        self._graph_seed_k = graph_seed_k
        self._graph_max_hops = graph_max_hops
        self._graph_decay = graph_decay
        self._graph_category_decay = graph_category_decay
        self._rrf_k = rrf_k
        self._structured_min_results = structured_min_results

    def run(
        self,
        query: str,
        k: int = 5,
        type: str | None = None,
        since: date | None = None,
        until: date | None = None,
    ) -> list[CandidateMatch]:
        if type is not None:
            structural_ids = self._metadata_repository.find_by_type_and_date(type, since, until)
            if len(structural_ids) >= self._structured_min_results:
                return [
                    CandidateMatch(concept_id=ConceptId(cid), score=1.0)
                    for cid in structural_ids[:k]
                ]

        vector = self._embedding.embed(query)
        semantic = self._vector_search.query(vector, k=self._pool_k)
        lexical = self._metadata_repository.search_fts(query, k=self._pool_k)

        fused = reciprocal_rank_fusion(
            [match.concept_id for match in semantic],
            [match.concept_id for match in lexical],
            k=self._rrf_k,
        )

        seed_ids = [str(match.concept_id) for match in fused[: self._graph_seed_k]]
        graph_scores = self._metadata_repository.expand_neighbors(
            seed_ids,
            max_hops=self._graph_max_hops,
            decay=self._graph_decay,
            category_decay=self._graph_category_decay,
        )

        # RRF scores (~1/rrf_k, e.g. ~0.03) and hop-decayed graph scores
        # (up to `graph_decay`, e.g. 0.5) are on wildly different scales —
        # naively taking max() would let graph expansion steamroll the
        # fused ranking rather than rerank *within* it. So: a fused hit
        # that's also graph-reachable gets boosted (multiplicatively, by up
        # to 2x — "more-linked context ranks higher" — bounded so it can't
        # leapfrog a much more relevant hit), and a graph-only discovery
        # (not in the fused set at all) is scaled below the weakest fused
        # score, ordered among themselves by decay — it extends the ranked
        # list, it doesn't get to outrank genuine semantic/lexical matches.
        fused_scores = {str(match.concept_id): match.score for match in fused}
        boosted = {
            cid: score * (1 + graph_scores.get(cid, 0.0)) for cid, score in fused_scores.items()
        }
        floor = min(fused_scores.values()) if fused_scores else None
        graph_only = {
            cid: (floor * score if floor is not None else score)
            for cid, score in graph_scores.items()
            if cid not in fused_scores
        }
        merged: dict[str, float] = {**boosted, **graph_only}

        results: list[CandidateMatch] = []
        for concept_id, score in sorted(merged.items(), key=lambda item: item[1], reverse=True):
            try:
                results.append(CandidateMatch(concept_id=ConceptId(concept_id), score=score))
            except ValueError:
                continue  # malformed link target (e.g. an unresolved relative path)
            if len(results) == k:
                break
        return results
