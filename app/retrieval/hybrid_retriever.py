from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
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
    def __init__(
        self,
        index_store: IndexStore,
        embedder: Optional[BaseEmbedder] = None,
        bm25_weight: Optional[float] = None,
        dense_weight: Optional[float] = None,
        top_k_bm25: Optional[int] = None,
        top_k_dense: Optional[int] = None,
        top_k_final: Optional[int] = None
    ):
        self.index_store = index_store
        self.embedder = embedder or get_embedder()
        
        self.bm25_weight = bm25_weight or settings.bm25_weight
        self.dense_weight = dense_weight or settings.dense_weight
        self.top_k_bm25 = top_k_bm25 or settings.retrieval_top_k_bm25
        self.top_k_dense = top_k_dense or settings.retrieval_top_k_dense
        self.top_k_final = top_k_final or settings.retrieval_top_k_final
    
    def _normalize_scores(self, scores: List[Tuple[str, float]]) -> Dict[str, float]:
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
    
    def retrieve(self, query: str) -> List[RetrievalResult]:
        bm25_results = self._bm25_retrieve(query)
        dense_results = self._dense_retrieve(query)
        
        bm25_normalized = self._normalize_scores(bm25_results)
        dense_normalized = self._normalize_scores(dense_results)
        
        all_chunk_ids = set(bm25_normalized.keys()) | set(dense_normalized.keys())
        
        fused_scores: Dict[str, Tuple[float, float, float]] = {}
        
        for chunk_id in all_chunk_ids:
            bm25_score = bm25_normalized.get(chunk_id, 0.0)
            dense_score = dense_normalized.get(chunk_id, 0.0)
            
            fused_score = self.bm25_weight * bm25_score + self.dense_weight * dense_score
            
            fused_scores[chunk_id] = (fused_score, bm25_score, dense_score)
        
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
                    dense_score=dense_score
                ))
        
        logger.info(f"Retrieved {len(results)} chunks for query: {query[:50]}...")
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
        
        for sub_query in sub_queries:
            results = self.retrieve(sub_query)
            for result in results:
                if result.chunk_id not in all_results or result.score > all_results[result.chunk_id].score:
                    all_results[result.chunk_id] = result
        
        sorted_results = sorted(
            all_results.values(),
            key=lambda x: x.score,
            reverse=True
        )[:self.top_k_final]
        
        return sorted_results