from typing import List, Optional, Dict, Any
from pathlib import Path

from app.schemas.query import QueryRequest, PlannerOutput
from app.schemas.response import ChatResponse
from app.schemas.citation import Citation
from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import get_embedder
from app.agents.planner_agent import PlannerAgent
from app.agents.reasoning_agent import ReasoningAgent, ReasoningOutput
from app.agents.citation_formatter import CitationFormatter
from app.core.config import settings
from app.core.logger import logger


class Orchestrator:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None
    ):
        self.index_store = index_store
        self.index_path = index_path or settings.indexes_dir
        
        self.retriever: Optional[HybridRetriever] = None
        self.planner = PlannerAgent()
        self.reasoning_agent = ReasoningAgent()
        self.citation_formatter = CitationFormatter()
        
        if self.index_store is None and Path(self.index_path).exists():
            self._load_index_store()
    
    def _load_index_store(self):
        try:
            self.index_store = IndexStore.load(self.index_path)
            self.retriever = HybridRetriever(
                index_store=self.index_store,
                embedder=get_embedder()
            )
            logger.info(f"Loaded index store from {self.index_path}")
        except Exception as e:
            logger.error(f"Failed to load index store: {e}")
    
    def is_ready(self) -> bool:
        return self.index_store is not None and self.retriever is not None
    
    def process_query(self, request: QueryRequest) -> ChatResponse:
        if not self.is_ready():
            return ChatResponse(
                query_type="error",
                answer="The system is not ready. Please build the index first.",
                citations=[],
                retrieved_chunks=[],
                uncertainty_note="Index not loaded."
            )
        
        planner_output = self.planner.plan(request.query)
        
        if planner_output.query_type == "multi_hop" and len(planner_output.sub_queries) > 1:
            retrieval_results = self.retriever.retrieve_for_sub_queries(planner_output.sub_queries)
        else:
            retrieval_results = self.retriever.retrieve(request.query)
        
        if planner_output.needs_second_retrieval and len(retrieval_results) < 3:
            logger.info("Performing second retrieval pass")
            additional_results = self.retriever.retrieve(request.query)
            existing_ids = {r.chunk_id for r in retrieval_results}
            for result in additional_results:
                if result.chunk_id not in existing_ids:
                    retrieval_results.append(result)
                    existing_ids.add(result.chunk_id)
        
        reasoning_output = self.reasoning_agent.reason(
            query=request.query,
            planner_output=planner_output,
            retrieval_results=retrieval_results
        )
        
        citations = self.citation_formatter.format_citations(
            [r for r in retrieval_results if r.chunk_id in reasoning_output.used_chunk_ids]
        )
        
        retrieved_chunks_data = [
            {
                "chunk_id": r.chunk_id,
                "rule_number": r.chunk.rule_number,
                "section_title": r.chunk.section_title,
                "text": r.chunk.text[:200] + "..." if len(r.chunk.text) > 200 else r.chunk.text,
                "score": r.score
            }
            for r in retrieval_results[:10]
        ]
        
        response = ChatResponse(
            query_type=planner_output.query_type,
            answer=reasoning_output.answer,
            citations=citations,
            retrieved_chunks=retrieved_chunks_data,
            uncertainty_note=reasoning_output.uncertainty_note,
            planner_output=planner_output
        )
        
        logger.info(f"Processed query: {request.query[:50]}... -> {planner_output.query_type}")
        return response


def create_orchestrator(index_path: Optional[Path] = None) -> Orchestrator:
    return Orchestrator(index_path=index_path)
