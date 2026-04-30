from typing import Dict, Any, Optional
from pathlib import Path

from langgraph.graph import StateGraph, END

from app.agents.graph_state import AgentState
from app.agents.planner_agent import PlannerAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.citation_formatter import CitationFormatter
from app.agents.coverage_checker import CoverageChecker
from app.agents.evidence_selector import EvidenceSelector
from app.agents.answer_verifier import AnswerVerifier
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import get_embedder
from app.schemas.query import PlannerOutput
from app.schemas.citation import Citation
from app.core.config import settings
from app.core.logger import logger


class GraphNodes:
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
        self.coverage_checker = CoverageChecker()
        self.evidence_selector = EvidenceSelector()
        self.answer_verifier = AnswerVerifier()
        
        if self.index_store is None and Path(self.index_path).exists():
            self._load_index_store()
    
    def _load_index_store(self):
        try:
            self.index_store = IndexStore.load(self.index_path)
            self.retriever = HybridRetriever(
                index_store=self.index_store,
                embedder=get_embedder()
            )
            logger.info(f"GraphNodes: Loaded index store from {self.index_path}")
        except Exception as e:
            logger.error(f"GraphNodes: Failed to load index store: {e}")
    
    def is_ready(self) -> bool:
        return self.index_store is not None and self.retriever is not None


def planner_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        
        planner_output = nodes.planner.plan(query)
        
        return {
            "planner_output": planner_output,
            "query_type": planner_output.query_type,
            "needs_second_retrieval": planner_output.needs_second_retrieval,
            "iteration_count": 0,
            "retrieval_rounds": []
        }
    
    return node


def retriever_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        if not nodes.is_ready():
            return {
                "error": "Index not loaded",
                "retrieved_chunks": []
            }
        
        query = state["query"]
        planner_output = state["planner_output"]
        
        if planner_output.query_type == "multi_hop" and len(planner_output.sub_queries) > 1:
            results = nodes.retriever.retrieve_for_sub_queries(planner_output.sub_queries)
        else:
            results = nodes.retriever.retrieve(query)
        
        chunks_data = [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.chunk.document_id,
                "rule_number": r.chunk.rule_number,
                "section_title": r.chunk.section_title,
                "chapter": r.chunk.chapter,
                "source_path": r.chunk.source_path,
                "text": r.chunk.text,
                "score": r.score
            }
            for r in results[:10]
        ]
        
        logger.info(f"Retriever node: retrieved {len(chunks_data)} chunks")
        
        return {
            "retrieved_chunks": chunks_data
        }
    
    return node


def coverage_checker_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        planner_output = state["planner_output"]
        chunks_data = state["retrieved_chunks"]
        
        if not chunks_data or not planner_output:
            return {
                "coverage_assessment": None,
                "needs_second_retrieval": False
            }
        
        results = [
            RetrievalResult(
                chunk_id=c["chunk_id"],
                chunk=nodes.index_store.get_chunk_by_id(c["chunk_id"]) if nodes.index_store else None,
                score=c["score"],
                bm25_score=0.0,
                dense_score=c["score"]
            )
            for c in chunks_data
            if nodes.index_store and nodes.index_store.get_chunk_by_id(c["chunk_id"])
        ]
        
        assessment = nodes.coverage_checker.assess(planner_output, results)
        
        return {
            "coverage_assessment": assessment.model_dump(),
            "needs_second_retrieval": assessment.needs_targeted_retrieval
        }
    
    return node


def evidence_selector_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        planner_output = state["planner_output"]
        chunks_data = state["retrieved_chunks"]
        
        if not chunks_data:
            return {"selected_evidence": None}
        
        results = [
            RetrievalResult(
                chunk_id=c["chunk_id"],
                chunk=nodes.index_store.get_chunk_by_id(c["chunk_id"]) if nodes.index_store else None,
                score=c["score"],
                bm25_score=0.0,
                dense_score=c["score"]
            )
            for c in chunks_data
            if nodes.index_store and nodes.index_store.get_chunk_by_id(c["chunk_id"])
        ]
        
        selected = nodes.evidence_selector.select(planner_output, results)
        
        return {
            "selected_evidence": selected.model_dump()
        }
    
    return node


def reasoning_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        planner_output = state["planner_output"]
        chunks_data = state["retrieved_chunks"]
        
        if not chunks_data:
            return {
                "answer": "I could not find relevant information to answer your question.",
                "uncertainty_note": "No relevant documents found in the knowledge base.",
                "citations": []
            }
        
        results = [
            RetrievalResult(
                chunk_id=c["chunk_id"],
                chunk=nodes.index_store.get_chunk_by_id(c["chunk_id"]) if nodes.index_store else None,
                score=c["score"],
                bm25_score=0.0,
                dense_score=c["score"]
            )
            for c in chunks_data
            if nodes.index_store and nodes.index_store.get_chunk_by_id(c["chunk_id"])
        ]
        
        reasoning_output = nodes.reasoning_agent.reason(
            query=query,
            planner_output=planner_output,
            retrieval_results=results
        )
        
        citations = nodes.citation_formatter.format_citations(
            [r for r in results if r.chunk_id in reasoning_output.used_chunk_ids]
        )
        
        return {
            "answer": reasoning_output.answer,
            "uncertainty_note": reasoning_output.uncertainty_note,
            "citations": citations
        }
    
    return node


def answer_verifier_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        answer = state.get("answer")
        chunks_data = state.get("retrieved_chunks", [])
        
        if not answer:
            return {
                "verification_result": None,
                "confidence_level": "low"
            }
        
        results = [
            RetrievalResult(
                chunk_id=c["chunk_id"],
                chunk=nodes.index_store.get_chunk_by_id(c["chunk_id"]) if nodes.index_store else None,
                score=c["score"],
                bm25_score=0.0,
                dense_score=c["score"]
            )
            for c in chunks_data
            if nodes.index_store and nodes.index_store.get_chunk_by_id(c["chunk_id"])
        ]
        
        verification = nodes.answer_verifier.verify(answer, results)
        
        return {
            "verification_result": verification.model_dump(),
            "confidence_level": verification.confidence_level
        }
    
    return node


def should_continue(state: AgentState) -> str:
    if state.get("error"):
        return "end"
    
    iteration_count = state.get("iteration_count", 0)
    needs_second_retrieval = state.get("needs_second_retrieval", False)
    
    if needs_second_retrieval and iteration_count < 1:
        return "retrieve_again"
    
    return "check_coverage"


def should_retrieve_targeted(state: AgentState) -> str:
    coverage = state.get("coverage_assessment")
    
    if not coverage:
        return "select_evidence"
    
    if coverage.get("needs_targeted_retrieval", False) and state.get("iteration_count", 0) < 2:
        return "retrieve_again"
    
    return "select_evidence"


def second_retrieval_node(nodes: GraphNodes) -> callable:
    def node(state: AgentState) -> Dict[str, Any]:
        if not nodes.is_ready():
            return {"iteration_count": state.get("iteration_count", 0) + 1}

        query = state["query"]
        existing_ids = {c["chunk_id"] for c in state["retrieved_chunks"]}
        coverage = state.get("coverage_assessment")

        # Use QueryRewriter for targeted retrieval if coverage gaps exist
        from app.agents.query_rewriter import QueryRewriter
        rewriter = QueryRewriter()

        missing_info = []
        if coverage and isinstance(coverage, dict):
            missing_info = coverage.get("missing_information", [])

        targeted_queries = rewriter.rewrite(
            original_query=query,
            missing_information=missing_info,
        )

        # Retrieve for each targeted query
        all_results = []
        for tq in targeted_queries:
            results = nodes.retriever.retrieve(tq)
            all_results.extend(results)

        # Deduplicate and filter already-seen chunks
        seen_ids = set()
        new_chunks = []
        for r in all_results:
            if r.chunk_id not in existing_ids and r.chunk_id not in seen_ids:
                seen_ids.add(r.chunk_id)
                new_chunks.append({
                    "chunk_id": r.chunk_id,
                    "document_id": r.chunk.document_id,
                    "rule_number": r.chunk.rule_number,
                    "section_title": r.chunk.section_title,
                    "chapter": r.chunk.chapter,
                    "source_path": r.chunk.source_path,
                    "text": r.chunk.text,
                    "score": r.score
                })

        logger.info(
            f"Second retrieval: {len(targeted_queries)} targeted queries, "
            f"found {len(new_chunks)} additional chunks"
        )

        round_info = {
            "round": state.get("iteration_count", 0) + 1,
            "queries": targeted_queries,
            "chunks_found": len(new_chunks)
        }

        return {
            "retrieved_chunks": new_chunks,
            "iteration_count": state.get("iteration_count", 0) + 1,
            "needs_second_retrieval": False,
            "retrieval_rounds": [round_info]
        }

    return node


def build_graph(nodes: GraphNodes) -> StateGraph:
    workflow = StateGraph(AgentState)
    
    workflow.add_node("planner", planner_node(nodes))
    workflow.add_node("retriever", retriever_node(nodes))
    workflow.add_node("coverage_checker", coverage_checker_node(nodes))
    workflow.add_node("evidence_selector", evidence_selector_node(nodes))
    workflow.add_node("reasoning", reasoning_node(nodes))
    workflow.add_node("answer_verifier", answer_verifier_node(nodes))
    workflow.add_node("second_retrieval", second_retrieval_node(nodes))
    
    workflow.set_entry_point("planner")
    
    workflow.add_edge("planner", "retriever")
    
    workflow.add_conditional_edges(
        "retriever",
        should_continue,
        {
            "retrieve_again": "second_retrieval",
            "check_coverage": "coverage_checker",
            "end": END
        }
    )
    
    workflow.add_edge("second_retrieval", "coverage_checker")
    
    workflow.add_conditional_edges(
        "coverage_checker",
        should_retrieve_targeted,
        {
            "retrieve_again": "second_retrieval",
            "select_evidence": "evidence_selector"
        }
    )
    
    workflow.add_edge("evidence_selector", "reasoning")
    
    workflow.add_edge("reasoning", "answer_verifier")
    
    workflow.add_edge("answer_verifier", END)
    
    return workflow.compile()


class LangGraphOrchestrator:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None
    ):
        self.nodes = GraphNodes(index_store=index_store, index_path=index_path)
        self.graph = build_graph(self.nodes)
    
    def is_ready(self) -> bool:
        return self.nodes.is_ready()
    
    def process_query(self, query: str) -> Dict[str, Any]:
        initial_state: AgentState = {
            "query": query,
            "planner_output": None,
            "retrieved_chunks": [],
            "citations": [],
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "retrieval_rounds": [],
            "route_decision": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
            "tool_calls": [],
            "tool_results": [],
        }
        
        final_state = self.graph.invoke(initial_state)
        
        return {
            "query_type": final_state.get("query_type", "unknown"),
            "answer": final_state.get("answer", "No answer generated."),
            "citations": final_state.get("citations", []),
            "retrieved_chunks": final_state.get("retrieved_chunks", []),
            "uncertainty_note": final_state.get("uncertainty_note"),
            "planner_output": final_state.get("planner_output"),
            "coverage_assessment": final_state.get("coverage_assessment"),
            "selected_evidence": final_state.get("selected_evidence"),
            "verification_result": final_state.get("verification_result"),
            "confidence_level": final_state.get("confidence_level"),
            "retrieval_rounds": final_state.get("retrieval_rounds", [])
        }
