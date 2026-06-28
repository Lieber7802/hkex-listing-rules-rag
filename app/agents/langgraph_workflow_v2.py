from __future__ import annotations

from typing import Dict, Any, Optional
from pathlib import Path
import uuid

from langgraph.graph import StateGraph, END

from app.agents.graph_state import AgentState
from app.agents.planner_agent import PlannerAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.citation_formatter import CitationFormatter, format_citations
from app.agents.coverage_checker import CoverageChecker
from app.agents.evidence_selector import EvidenceSelector, select_evidence
from app.agents.answer_verifier import AnswerVerifier
from app.agents.tool_input_extraction_node import tool_input_extraction_node, extract_tool_inputs
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import get_embedder
from app.schemas.planning import RouteDecision, ToolDecision
from app.schemas.query import PlannerOutput
from app.schemas.citation import Citation
from app.tools.base_tool import ToolRegistry
from app.core.config import settings
from app.core.logger import logger


MAX_RETRIEVAL_ROUNDS = 2


class GraphNodes:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
        use_llm_planner: bool = True,
        **kwargs,
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
        self.tool_registry = ToolRegistry()

        if self.index_store is None and Path(self.index_path).exists():
            self._load_index_store()
        self._register_tools()

    def _load_index_store(self):
        try:
            self.index_store = IndexStore.load(self.index_path)
            self.retriever = HybridRetriever(index_store=self.index_store, embedder=get_embedder())
            logger.info(f"GraphNodes: Loaded index store from {self.index_path}")
        except Exception as e:
            logger.error(f"GraphNodes: Failed to load index store: {e}")

    def _register_tools(self):
        from app.tools.size_test_calculator import SizeTestCalculatorTool
        from app.tools.transaction_classifier import TransactionClassifierTool
        from app.tools.disclosure_checklist import DisclosureChecklistTool
        from app.tools.rule_lookup import RuleLookupTool

        self.tool_registry.register(SizeTestCalculatorTool())
        self.tool_registry.register(TransactionClassifierTool())
        self.tool_registry.register(DisclosureChecklistTool())
        self.tool_registry.register(RuleLookupTool(index_store=self.index_store))

    def is_ready(self) -> bool:
        return self.index_store is not None and self.retriever is not None


def planner_agent_v2_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        planner_output = nodes.planner.plan(query)

        tool_name = planner_output.tool_name if planner_output.requires_tool else None
        tool_mode = planner_output.tool_mode if planner_output.requires_tool else "none"
        tool_inputs_hint: Dict[str, Any] = {}
        if planner_output.requires_tool and tool_name:
            tool_inputs_hint = extract_tool_inputs(query, tool_name)

        route_decision = RouteDecision(
            query_type=planner_output.query_type,
            intent=planner_output.intent,
            requires_decomposition=False,
            retrieval_strategy=planner_output.retrieval_strategy,
            tool_decision=ToolDecision(
                requires_tool=planner_output.requires_tool,
                tool_name=tool_name,
                tool_mode=tool_mode,
                tool_inputs_hint=tool_inputs_hint,
            ),
            answer_format=planner_output.answer_format,
            route_reason=planner_output.reason,
            fallback_used=False,
            sub_queries=list(planner_output.sub_queries),
        )

        logger.info(
            f"Planner v2: query_type={route_decision.query_type}, "
            f"intent={route_decision.intent}, requires_tool={route_decision.tool_decision.requires_tool}, "
            f"sub_queries={len(route_decision.sub_queries)}"
        )

        return {
            "route_decision": route_decision.model_dump(),
            "query_type": route_decision.query_type,
            "iteration_count": 0,
            "retrieval_rounds": [],
        }

    return node


def retriever_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        if not nodes.is_ready():
            return {"error": "Index not loaded", "retrieved_chunks": []}

        query = state["query"]
        route_dict = state.get("route_decision")
        chat_history = state.get("chat_history")

        original_query = None
        if chat_history:
            from app.agents.contextual_query_rewriter import ContextualQueryRewriter
            from app.models.conversation import ConversationTurn

            rewriter = ContextualQueryRewriter()
            history_turns = [ConversationTurn(role=h["role"], content=h["content"]) for h in chat_history]
            rewritten = rewriter.rewrite(query, history_turns)
            if rewritten != query:
                original_query = query
                query = rewritten

        route_decision = RouteDecision(**route_dict) if route_dict else None
        sub_queries = route_decision.sub_queries if route_decision else []

        results = []
        if sub_queries and route_decision and route_decision.query_type == "multi_hop":
            results = nodes.retriever.retrieve_for_sub_queries(sub_queries)

        if not results:
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
                "score": r.score,
                "bm25_score": getattr(r, "bm25_score", r.score),
                "dense_score": getattr(r, "dense_score", r.score),
            }
            for r in results[:10]
        ]

        logger.info(f"Retriever node: retrieved {len(chunks_data)} chunks")

        result = {
            "retrieved_chunks": chunks_data,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }
        if original_query:
            result["original_query"] = original_query
            result["query"] = query
        return result

    return node


def coverage_checker_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]

        if not chunks_data or not route_dict:
            return {"coverage_assessment": None, "needs_second_retrieval": False}

        route_decision = RouteDecision(**route_dict)

        if route_decision.tool_decision and route_decision.tool_decision.tool_mode == "tool_only":
            return {"coverage_assessment": None, "needs_second_retrieval": False}

        planner_output = route_decision.to_planner_output()
        results = _reconstruct_results(chunks_data, nodes.index_store)
        assessment = nodes.coverage_checker.assess(planner_output, results)
        return {
            "coverage_assessment": assessment.model_dump(),
            "needs_second_retrieval": assessment.needs_targeted_retrieval,
        }

    return node


def evidence_selector_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        tool_results = state.get("tool_results", [])

        if not chunks_data and tool_results:
            return {"selected_evidence": None}

        route_decision = RouteDecision(**route_dict) if route_dict else None
        planner_output = route_decision.to_planner_output() if route_decision else None

        results = _reconstruct_results(chunks_data, nodes.index_store)

        if planner_output:
            selected = nodes.evidence_selector.select(planner_output, results)
        else:
            selected = select_evidence(results)

        return {"selected_evidence": selected.model_dump()}

    return node


def reasoning_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        tool_results = state.get("tool_results", [])

        route_decision = RouteDecision(**route_dict) if route_dict else None
        planner_output = route_decision.to_planner_output() if route_decision else PlannerOutput(
            query_type="direct", sub_queries=[], intent="general"
        )

        results = _reconstruct_results(chunks_data, nodes.index_store)

        reasoning_output = nodes.reasoning_agent.reason(
            query=query,
            planner_output=planner_output,
            retrieval_results=results,
            chat_history=state.get("chat_history"),
            tool_results=tool_results if tool_results else None,
        )

        citations = format_citations(
            [r for r in results if r.chunk_id in reasoning_output.used_chunk_ids]
        )

        if tool_results and not results:
            for tr in tool_results:
                if tr.get("success") and tr.get("tool_name") == "rule_lookup":
                    output = tr.get("output", {})
                    for chunk_data in output.get("chunks", []):
                        chunk = nodes.index_store.get_chunk_by_id(chunk_data.get("chunk_id")) if nodes.index_store else None
                        if chunk:
                            citations.append(Citation(
                                chunk_id=chunk_data.get("chunk_id", ""),
                                document_id=chunk_data.get("source_path", ""),
                                rule_number=chunk_data.get("rule_number"),
                                section_title=chunk_data.get("section_title"),
                                chapter=chunk_data.get("chapter"),
                                source_path=chunk_data.get("source_path", ""),
                                snippet=chunk_data.get("text", "")[:300],
                                score=1.0,
                            ))

        return {
            "answer": reasoning_output.answer,
            "uncertainty_note": reasoning_output.uncertainty_note,
            "citations": citations,
        }

    return node


def answer_verifier_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        answer = state.get("answer")
        chunks_data = state.get("retrieved_chunks", [])
        tool_results = state.get("tool_results", [])

        if not answer:
            return {"verification_result": None, "confidence_level": "low"}

        results = _reconstruct_results(chunks_data, nodes.index_store)

        if not results and tool_results:
            successful_tools = [r for r in tool_results if r.get("success")]
            if successful_tools:
                return {
                    "verification_result": {
                        "is_supported": True,
                        "unsupported_claims": [],
                        "contradictions": [],
                        "confidence_level": "high",
                        "summary": f"Answer is supported by tool execution ({len(successful_tools)} tool(s) executed successfully).",
                    },
                    "confidence_level": "high",
                }

        verification = nodes.answer_verifier.verify(answer, results)
        return {
            "verification_result": verification.model_dump(),
            "confidence_level": verification.confidence_level,
        }

    return node


def _reconstruct_results(chunks_data, index_store):
    """Reconstruct RetrievalResult list from serialized chunks, preserving per-signal scores."""
    results = []
    for c in chunks_data:
        chunk = index_store.get_chunk_by_id(c["chunk_id"]) if index_store else None
        if chunk:
            results.append(RetrievalResult(
                chunk_id=c["chunk_id"],
                chunk=chunk,
                score=c["score"],
                bm25_score=c.get("bm25_score", c["score"]),
                dense_score=c.get("dense_score", c["score"]),
            ))
    return results


def _execute_single_tool(
    nodes: GraphNodes, tool_name: str, inputs: Dict[str, Any], call_id: str,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    tool = nodes.tool_registry.get(tool_name)
    if tool is None:
        return {
            "call_id": call_id, "tool_name": tool_name,
            "success": False, "output": None,
            "error": f"Tool not found: '{tool_name}'",
        }

    validation_errors = tool.validate_inputs(inputs)
    if validation_errors:
        if query and (not inputs or len(inputs) <= 1):
            recovered = extract_tool_inputs(query, tool_name)
            if recovered:
                merged = {**recovered, **{k: v for k, v in inputs.items() if v}}
                retry_errors = tool.validate_inputs(merged)
                if not retry_errors:
                    logger.info(f"Fallback recovery succeeded for {tool_name}")
                    try:
                        output = tool.run(merged)
                        return {
                            "call_id": call_id, "tool_name": tool_name,
                            "success": True, "output": output, "error": None,
                            "_recovered": True,
                        }
                    except Exception as e:
                        return {
                            "call_id": call_id, "tool_name": tool_name,
                            "success": False, "output": None,
                            "error": f"Tool execution error after recovery: {str(e)}",
                        }
        return {
            "call_id": call_id, "tool_name": tool_name,
            "success": False, "output": None,
            "error": f"Input validation failed: {'; '.join(validation_errors)}",
        }

    try:
        output = tool.run(inputs)
        return {
            "call_id": call_id, "tool_name": tool_name,
            "success": True, "output": output, "error": None,
        }
    except Exception as e:
        return {
            "call_id": call_id, "tool_name": tool_name,
            "success": False, "output": None,
            "error": f"Tool execution error: {str(e)}",
        }


def tool_executor_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        from app.tools.tool_chain import should_chain, get_next_chain_target

        route_dict = state.get("route_decision")
        if not route_dict:
            return {"tool_calls": [], "tool_results": []}

        route_decision = RouteDecision(**route_dict)
        tool_decision = route_decision.tool_decision

        if not tool_decision or not tool_decision.requires_tool:
            return {"tool_calls": [], "tool_results": []}

        tool_name = tool_decision.tool_name or ""
        tool_inputs = dict(tool_decision.tool_inputs_hint) if tool_decision.tool_inputs_hint else {}

        all_tool_calls = []
        all_tool_results = []
        user_context = dict(tool_inputs)
        query_text = state.get("query", "") or state.get("original_query", "")

        call_id = str(uuid.uuid4())[:8]
        tool_call = {"call_id": call_id, "tool_name": tool_name, "inputs": tool_inputs}
        all_tool_calls.append(tool_call)

        primary_result = _execute_single_tool(nodes, tool_name, tool_inputs, call_id, query_text)
        all_tool_results.append(primary_result)

        if primary_result["success"] and should_chain(tool_name, primary_result["output"]):
            current_tool = tool_name
            current_output = primary_result["output"]
            visited = {tool_name}

            while True:
                next_step = get_next_chain_target(current_tool, current_output, user_context, visited)
                if next_step is None:
                    break

                target_name, target_inputs = next_step
                chain_call_id = str(uuid.uuid4())[:8]
                chain_call = {"call_id": chain_call_id, "tool_name": target_name, "inputs": target_inputs}
                all_tool_calls.append(chain_call)

                chain_result = _execute_single_tool(nodes, target_name, target_inputs, chain_call_id)
                all_tool_results.append(chain_result)

                if chain_result["success"]:
                    visited.add(target_name)
                    current_tool = target_name
                    current_output = chain_result["output"]
                else:
                    break

        logger.info(f"Tool executor: executed {len(all_tool_calls)} tool(s)")
        return {"tool_calls": all_tool_calls, "tool_results": all_tool_results}

    return node


def should_route(state: AgentState) -> str:
    route_dict = state.get("route_decision")
    if not route_dict:
        return "retrieve"

    route_decision = RouteDecision(**route_dict)
    if route_decision.tool_decision and route_decision.tool_decision.requires_tool:
        return "execute_tool"
    return "retrieve"


def tool_mode_router(state: AgentState) -> str:
    route_dict = state.get("route_decision")
    if not route_dict:
        return "retrieve"

    route_decision = RouteDecision(**route_dict)
    tool_decision = route_decision.tool_decision

    if tool_decision and tool_decision.tool_mode == "tool_only":
        return "select"
    return "retrieve"


def build_graph(nodes: GraphNodes) -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("planner_agent_v2", planner_agent_v2_node(nodes))
    workflow.add_node("tool_input_extraction", tool_input_extraction_node(nodes))
    workflow.add_node("tool_executor", tool_executor_node(nodes))
    workflow.add_node("retriever", retriever_node(nodes))
    workflow.add_node("coverage_checker", coverage_checker_node(nodes))
    workflow.add_node("evidence_selector", evidence_selector_node(nodes))
    workflow.add_node("reasoning", reasoning_node(nodes))
    workflow.add_node("answer_verifier", answer_verifier_node(nodes))

    workflow.set_entry_point("planner_agent_v2")

    workflow.add_conditional_edges(
        "planner_agent_v2",
        should_route,
        {
            "execute_tool": "tool_input_extraction",
            "retrieve": "retriever",
        },
    )

    workflow.add_edge("tool_input_extraction", "tool_executor")

    workflow.add_conditional_edges(
        "tool_executor",
        tool_mode_router,
        {
            "select": "evidence_selector",
            "retrieve": "retriever",
        },
    )

    workflow.add_edge("retriever", "coverage_checker")

    workflow.add_conditional_edges(
        "coverage_checker",
        lambda state: (
            "retrieve"
            if state.get("needs_second_retrieval")
            and state.get("iteration_count", 0) < MAX_RETRIEVAL_ROUNDS
            else "select"
        ),
        {
            "retrieve": "retriever",
            "select": "evidence_selector",
        },
    )

    workflow.add_edge("evidence_selector", "reasoning")
    workflow.add_edge("reasoning", "answer_verifier")
    workflow.add_edge("answer_verifier", END)

    return workflow.compile()


class LangGraphOrchestratorV2:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
        use_llm_planner: bool = True,
    ):
        self.nodes = GraphNodes(index_store=index_store, index_path=index_path)
        self.graph = build_graph(self.nodes)
        self.use_llm_planner = use_llm_planner

    def is_ready(self) -> bool:
        return self.nodes.is_ready()

    def process_query(
        self,
        query: str,
        use_llm_planner: bool = True,
        conversation_id: Optional[str] = None,
        chat_history: Optional[list] = None,
    ) -> Dict[str, Any]:
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
            "use_llm_planner": use_llm_planner,
            "route_retry_count": 0,
            "tool_calls": [],
            "tool_results": [],
            "extraction_log": None,
            "conversation_id": conversation_id,
            "chat_history": chat_history,
            "original_query": None,
        }

        final_state = self.graph.invoke(initial_state)

        return {
            "query_type": final_state.get("query_type", "unknown"),
            "answer": final_state.get("answer", "No answer generated."),
            "citations": final_state.get("citations", []),
            "retrieved_chunks": final_state.get("retrieved_chunks", []),
            "uncertainty_note": final_state.get("uncertainty_note"),
            "route_decision": final_state.get("route_decision"),
            "decomposition_plan": final_state.get("decomposition_plan"),
            "route_validation": final_state.get("route_validation"),
            "decomposition_validation": final_state.get("decomposition_validation"),
            "coverage_assessment": final_state.get("coverage_assessment"),
            "selected_evidence": final_state.get("selected_evidence"),
            "verification_result": final_state.get("verification_result"),
            "confidence_level": final_state.get("confidence_level"),
            "retrieval_rounds": final_state.get("retrieval_rounds", []),
            "tool_calls": final_state.get("tool_calls", []),
            "tool_results": final_state.get("tool_results", []),
            "extraction_log": final_state.get("extraction_log"),
            "conversation_id": final_state.get("conversation_id"),
        }
