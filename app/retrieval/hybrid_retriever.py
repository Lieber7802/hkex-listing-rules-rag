from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.embedder import BaseEmbedder, get_embedder
from app.retrieval.index_store import IndexStore
from app.core.config import settings
from app.core.logger import logger


@dataclass
class RetrievalResult:
    chunk_id: str
    chunk: Chunk
    score: float
    bm25_score: float
    dense_score: float


class HybridRetriever:
    """Hybrid retriever combining BM25 (lexical) and dense (semantic) retrieval
    using Reciprocal Rank Fusion (RRF).

    RRF formula: score(d) = sum over lists L of 1 / (k + rank_L(d))
    where k is a smoothing constant (default 60, per the original paper).
    """

    def __init__(
        self,
        index_store: IndexStore,
        embedder: Optional[BaseEmbedder] = None,
        top_k_bm25: Optional[int] = None,
        top_k_dense: Optional[int] = None,
        top_k_final: Optional[int] = None,
        rrf_k: Optional[int] = None,
    ):
        self.index_store = index_store
        self.embedder = embedder or get_embedder()
        self.top_k_bm25 = top_k_bm25 or settings.retrieval_top_k_bm25
        self.top_k_dense = top_k_dense or settings.retrieval_top_k_dense
        self.top_k_final = top_k_final or settings.retrieval_top_k_final
        self.rrf_k = rrf_k if rrf_k is not None else getattr(settings, "rrf_k", 20)

    def _normalize_scores(self, scores: List[Tuple[str, float]]) -> Dict[str, float]:
        """Min-max normalize raw scores to [0, 1].

        Still used to populate bm25_score / dense_score fields on
        RetrievalResult so downstream components (CoverageChecker,
        EvidenceSelector) can inspect per-signal scores.
        """
        if not scores:
            return {}

        score_values = [s for _, s in scores]
        min_score = min(score_values)
        max_score = max(score_values)

        if max_score == min_score:
            return {chunk_id: 1.0 for chunk_id, _ in scores}

        return {
            chunk_id: (score - min_score) / (max_score - min_score)
            for chunk_id, score in scores
        }

    def _rrf_fuse(
        self,
        bm25_results: List[Tuple[str, float]],
        dense_results: List[Tuple[str, float]],
    ) -> Dict[str, Tuple[float, float, float]]:
        """Fuse two ranked lists using Reciprocal Rank Fusion.

        Args:
            bm25_results: BM25 results sorted by score descending.
            dense_results: Dense results sorted by score descending.

        Returns:
            Dict mapping chunk_id -> (rrf_score, normalized_bm25, normalized_dense)
        """
        k = self.rrf_k

        # Build rank maps (1-indexed: rank 1 = best)
        bm25_rank: Dict[str, int] = {}
        for rank, (chunk_id, _score) in enumerate(bm25_results, start=1):
            bm25_rank[chunk_id] = rank

        dense_rank: Dict[str, int] = {}
        for rank, (chunk_id, _score) in enumerate(dense_results, start=1):
            dense_rank[chunk_id] = rank

        # Normalized scores for per-signal fields
        bm25_normalized = self._normalize_scores(bm25_results)
        dense_normalized = self._normalize_scores(dense_results)

        # Compute RRF scores
        all_chunk_ids = set(bm25_rank.keys()) | set(dense_rank.keys())
        fused: Dict[str, Tuple[float, float, float]] = {}

        for chunk_id in all_chunk_ids:
            rrf_score = 0.0
            if chunk_id in bm25_rank:
                rrf_score += 1.0 / (k + bm25_rank[chunk_id])
            if chunk_id in dense_rank:
                rrf_score += 1.0 / (k + dense_rank[chunk_id])

            bm25_norm = bm25_normalized.get(chunk_id, 0.0)
            dense_norm = dense_normalized.get(chunk_id, 0.0)
            fused[chunk_id] = (rrf_score, bm25_norm, dense_norm)

        return fused

    def retrieve(self, query: str) -> List[RetrievalResult]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            bm25_future = executor.submit(self._bm25_retrieve, query)
            dense_future = executor.submit(self._dense_retrieve, query)
            bm25_results = bm25_future.result()
            dense_results = dense_future.result()

        fused_scores = self._rrf_fuse(bm25_results, dense_results)

        sorted_chunks = sorted(
            fused_scores.items(),
            key=lambda x: x[1][0],
            reverse=True
        )[:self.top_k_final]

        results = []
        for chunk_id, (fused_score, bm25_score, dense_score) in sorted_chunks:
            chunk = self.index_store.get_chunk_by_id(chunk_id)
            if chunk:
                results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    chunk=chunk,
                    score=fused_score,
                    bm25_score=bm25_score,
                    dense_score=dense_score,
                ))

        logger.info(f"Retrieved {len(results)} chunks (RRF k={self.rrf_k}) for query: {query[:50]}...")
        return results

    def _bm25_retrieve(self, query: str) -> List[Tuple[str, float]]:
        if self.index_store.bm25_index is None:
            return []

        return self.index_store.bm25_index.search(query, top_k=self.top_k_bm25)

    def _dense_retrieve(self, query: str) -> List[Tuple[str, float]]:
        if self.index_store.vector_index is None:
            return []

        query_embedding = self.embedder.embed_single(query)
        return self.index_store.vector_index.search(query_embedding, top_k=self.top_k_dense)

    def retrieve_for_sub_queries(self, sub_queries: List[str]) -> List[RetrievalResult]:
        all_results: Dict[str, RetrievalResult] = {}
        per_query_min = max(3, self.top_k_final // max(len(sub_queries), 1))

        for sub_query in sub_queries:
            results = self.retrieve(sub_query)
            for result in results[:per_query_min + 2]:
                if result.chunk_id not in all_results or result.score > all_results[result.chunk_id].score:
                    all_results[result.chunk_id] = result

        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x.score,
            reverse=True
        )[:self.top_k_final]

        return sorted_results
