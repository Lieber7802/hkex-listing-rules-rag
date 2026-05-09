from typing import Dict, Any, Optional
from pathlib import Path

from langgraph.graph import StateGraph, END

from app.agents.graph_state import AgentState
from app.agents.llm_route_planner import LLMRoutePlanner
from app.agents.route_validator import HeuristicRouteValidator
from app.agents.task_decomposer import TaskDecomposer
from app.agents.decomposition_validator import DecompositionValidator
from app.agents.planner_agent import PlannerAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.citation_formatter import CitationFormatter
from app.agents.coverage_checker import CoverageChecker
from app.agents.evidence_selector import EvidenceSelector
from app.agents.answer_verifier import AnswerVerifier
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import get_embedder
from app.schemas.planning import RouteDecision
from app.tools.base_tool import ToolRegistry
from app.core.config import settings
from app.core.logger import logger


class GraphNodes:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
        use_llm_planner: bool = True
    ):
        self.index_store = index_store
        self.index_path = index_path or settings.indexes_dir
        self.retriever: Optional[HybridRetriever] = None
        self.use_llm_planner = use_llm_planner
        
        self.llm_route_planner = LLMRoutePlanner()
        self.route_validator = HeuristicRouteValidator()
        self.task_decomposer = TaskDecomposer()
        self.decomposition_validator = DecompositionValidator()
        
        self.heuristic_planner = PlannerAgent()
        self.reasoning_agent = ReasoningAgent()
        self.citation_formatter = CitationFormatter()
        self.coverage_checker = CoverageChecker()
        self.evidence_selector = EvidenceSelector()
        self.answer_verifier = AnswerVerifier()

        # Tool registry
        self.tool_registry = ToolRegistry()

        if self.index_store is None and Path(self.index_path).exists():
            self._load_index_store()

        self._register_tools()
    
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

    def _register_tools(self):
        """Register all HKEX tools in the tool registry."""
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


def llm_route_planner_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        use_llm = state.get("use_llm_planner", True)
        retry_count = state.get("route_retry_count", 0)

        if use_llm and nodes.use_llm_planner:
            route_decision = nodes.llm_route_planner.plan(query)
        else:
            planner_output = nodes.heuristic_planner.plan(query)
            from app.schemas.planning import ToolDecision
            route_decision = RouteDecision(
                query_type=planner_output.query_type,
                intent=planner_output.intent,
                requires_decomposition=planner_output.query_type == "multi_hop",
                retrieval_strategy=planner_output.retrieval_strategy,
                tool_decision=ToolDecision(
                    requires_tool=planner_output.requires_tool,
                    tool_name=planner_output.tool_name,
                    tool_mode=planner_output.tool_mode if planner_output.requires_tool else "none",
                ),
                answer_format=planner_output.answer_format,
                route_reason=planner_output.reason,
                fallback_used=True
            )

        return {
            "route_decision": route_decision.model_dump(),
            "query_type": route_decision.query_type,
            "use_llm_planner": use_llm,
            "route_retry_count": retry_count + 1,
        }

    return node


def route_validator_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        query = state["query"]
        
        if not route_dict:
            return {"route_validation": None}
        
        route_decision = RouteDecision(**route_dict)
        validation = nodes.route_validator.validate(route_decision, query)
        
        return {
            "route_validation": validation.model_dump()
        }
    
    return node


def task_decomposer_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        query = state["query"]
        
        if not route_dict:
            return {"decomposition_plan": None}
        
        route_decision = RouteDecision(**route_dict)
        
        if not route_decision.requires_decomposition:
            return {"decomposition_plan": None}
        
        decomposition = nodes.task_decomposer.decompose(query, route_decision)
        
        return {
            "decomposition_plan": decomposition.model_dump()
        }
    
    return node


def decomposition_validator_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        decomp_dict = state.get("decomposition_plan")
        
        if not decomp_dict:
            return {"decomposition_validation": None}
        
        from app.schemas.planning import DecompositionPlan, RouteDecision
        decomposition = DecompositionPlan(**decomp_dict)
        route = RouteDecision(**route_dict) if route_dict else None
        
        validation = nodes.decomposition_validator.validate(decomposition, route)
        
        return {
            "decomposition_validation": validation.model_dump()
        }
    
    return node


def retriever_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        if not nodes.is_ready():
            return {
                "error": "Index not loaded",
                "retrieved_chunks": []
            }

        query = state["query"]
        chat_history = state.get("chat_history")
        route_dict = state.get("route_decision")
        decomp_dict = state.get("decomposition_plan")

        # Contextual query rewriting for multi-turn (resolve coreferences)
        original_query = None
        if chat_history:
            from app.agents.contextual_query_rewriter import ContextualQueryRewriter
            from app.models.conversation import ConversationTurn

            rewriter = ContextualQueryRewriter()
            history_turns = [
                ConversationTurn(role=h["role"], content=h["content"])
                for h in chat_history
            ]
            rewritten = rewriter.rewrite(query, history_turns)
            if rewritten != query:
                original_query = query
                query = rewritten

        results = []

        if decomp_dict:
            from app.schemas.planning import DecompositionPlan
            decomp = DecompositionPlan(**decomp_dict)
            queries = [task.query for task in decomp.subtasks if task.type == "retrieval"]
            if queries:
                results = nodes.retriever.retrieve_for_sub_queries(queries)

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
                "score": r.score
            }
            for r in results[:10]
        ]

        logger.info(f"Retriever node: retrieved {len(chunks_data)} chunks")

        result = {"retrieved_chunks": chunks_data}
        if original_query:
            result["original_query"] = original_query
            result["query"] = query  # Update query for downstream nodes
        return result

    return node


def coverage_checker_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        
        if not chunks_data or not route_dict:
            return {
                "coverage_assessment": None,
                "needs_second_retrieval": False
            }
        
        from app.schemas.planning import RouteDecision
        route_decision = RouteDecision(**route_dict)
        
        from app.schemas.query import PlannerOutput
        planner_output = PlannerOutput(
            query_type=route_decision.query_type,
            sub_queries=[],
            needs_second_retrieval=False,
            reason=route_decision.route_reason or "",
            intent=route_decision.intent,
            sub_tasks=[],
            retrieval_strategy=route_decision.retrieval_strategy,
            requires_tool=route_decision.tool_decision.requires_tool,
            evidence_requirements={},
            answer_format=route_decision.answer_format
        )
        
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


def evidence_selector_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        
        if not chunks_data:
            return {"selected_evidence": None}
        
        from app.schemas.planning import RouteDecision
        route_decision = RouteDecision(**route_dict) if route_dict else None
        
        from app.schemas.query import PlannerOutput
        planner_output = PlannerOutput(
            query_type=route_decision.query_type if route_decision else "direct",
            sub_queries=[],
            needs_second_retrieval=False,
            reason="",
            intent=route_decision.intent if route_decision else "general",
            sub_tasks=[],
            retrieval_strategy=route_decision.retrieval_strategy if route_decision else "single_pass",
            requires_tool=False,
            evidence_requirements={},
            answer_format="concise_with_citations"
        )
        
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


def reasoning_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        tool_results = state.get("tool_results", [])

        # If no chunks but tool results exist, format tool output as answer
        if not chunks_data and tool_results:
            successful_results = [r for r in tool_results if r.get("success")]
            if successful_results:
                import json
                tool_output_str = json.dumps(successful_results[0]["output"], indent=2, ensure_ascii=False)
                return {
                    "answer": f"Tool execution result:\n\n{tool_output_str}",
                    "uncertainty_note": None,
                    "citations": []
                }

        if not chunks_data:
            return {
                "answer": "I could not find relevant information to answer your question.",
                "uncertainty_note": "No relevant documents found in the knowledge base.",
                "citations": []
            }
        
        from app.schemas.planning import RouteDecision
        route_decision = RouteDecision(**route_dict) if route_dict else None
        
        from app.schemas.query import PlannerOutput
        planner_output = PlannerOutput(
            query_type=route_decision.query_type if route_decision else "direct",
            sub_queries=[],
            needs_second_retrieval=False,
            reason="",
            intent=route_decision.intent if route_decision else "general",
            sub_tasks=[],
            retrieval_strategy=route_decision.retrieval_strategy if route_decision else "single_pass",
            requires_tool=False,
            evidence_requirements={},
            answer_format=route_decision.answer_format if route_decision else "concise_with_citations"
        )
        
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
            retrieval_results=results,
            chat_history=state.get("chat_history"),
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


def answer_verifier_node(nodes: GraphNodes):
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


def should_decompose(state: AgentState) -> str:
    route_dict = state.get("route_decision")
    if not route_dict:
        return "retrieve"

    from app.schemas.planning import RouteDecision
    route = RouteDecision(**route_dict)

    if route.requires_decomposition:
        return "decompose"
    return "retrieve"


def heuristic_fallback_node(nodes: GraphNodes):
    """Produces a route decision using pure heuristic when LLM routing fails validation."""
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        planner_output = nodes.heuristic_planner.plan(query)

        from app.schemas.planning import ToolDecision
        route_decision = RouteDecision(
            query_type=planner_output.query_type,
            intent=planner_output.intent,
            requires_decomposition=planner_output.query_type == "multi_hop",
            retrieval_strategy=planner_output.retrieval_strategy,
            tool_decision=ToolDecision(
                requires_tool=planner_output.requires_tool,
                tool_name=planner_output.tool_name,
                tool_mode=planner_output.tool_mode if planner_output.requires_tool else "none",
            ),
            answer_format=planner_output.answer_format,
            route_reason=f"Heuristic fallback: {planner_output.reason}",
            fallback_used=True
        )

        logger.info(f"Heuristic fallback produced route: {route_decision.query_type}/{route_decision.intent}")

        return {
            "route_decision": route_decision.model_dump(),
            "query_type": route_decision.query_type,
        }

    return node


def decompose_router_node(nodes: GraphNodes):
    """Pass-through node serving as convergence point for should_route branching."""
    def node(state: AgentState) -> Dict[str, Any]:
        return {}

    return node


def _execute_single_tool(
    nodes: 'GraphNodes', tool_name: str, inputs: Dict[str, Any], call_id: str
) -> Dict[str, Any]:
    """Execute a single tool and return the result dict."""
    tool = nodes.tool_registry.get(tool_name)
    if tool is None:
        return {
            "call_id": call_id,
            "tool_name": tool_name,
            "success": False,
            "output": None,
            "error": f"Tool not found: '{tool_name}'",
        }

    validation_errors = tool.validate_inputs(inputs)
    if validation_errors:
        return {
            "call_id": call_id,
            "tool_name": tool_name,
            "success": False,
            "output": None,
            "error": f"Input validation failed: {'; '.join(validation_errors)}",
        }

    try:
        output = tool.run(inputs)
        return {
            "call_id": call_id,
            "tool_name": tool_name,
            "success": True,
            "output": output,
            "error": None,
        }
    except Exception as e:
        return {
            "call_id": call_id,
            "tool_name": tool_name,
            "success": False,
            "output": None,
            "error": f"Tool execution error: {str(e)}",
        }


def tool_executor_node(nodes: GraphNodes):
    """Executes the tool specified in route_decision.tool_decision.

    Supports tool chaining: if a tool's output can feed a downstream tool,
    executes the chain automatically (e.g., size_test → classifier → checklist).
    """
    def node(state: AgentState) -> Dict[str, Any]:
        import uuid
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

        # User context for chain defaults (e.g., transaction_type, is_connected)
        user_context = dict(tool_inputs)

        # === Execute primary tool ===
        call_id = str(uuid.uuid4())[:8]
        tool_call = {"call_id": call_id, "tool_name": tool_name, "inputs": tool_inputs}
        all_tool_calls.append(tool_call)

        primary_result = _execute_single_tool(nodes, tool_name, tool_inputs, call_id)
        all_tool_results.append(primary_result)

        # === Chain execution ===
        if primary_result["success"] and should_chain(tool_name, primary_result["output"]):
            current_tool = tool_name
            current_output = primary_result["output"]
            visited = {tool_name}

            while True:
                next_step = get_next_chain_target(
                    current_tool, current_output, user_context, visited
                )
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
                    break  # Stop chain on failure

        logger.info(f"Tool executor: executed {len(all_tool_calls)} tool(s)")
        return {"tool_calls": all_tool_calls, "tool_results": all_tool_results}

    return node


def tool_mode_router(state: AgentState) -> str:
    """Route after tool execution: tool_only skips retrieval, tool_plus_retrieval continues."""
    route_dict = state.get("route_decision")
    if not route_dict:
        return "retrieve"

    route_decision = RouteDecision(**route_dict)
    tool_decision = route_decision.tool_decision

    if tool_decision and tool_decision.tool_mode == "tool_only":
        return "select"
    return "retrieve"


def should_route(state: AgentState) -> str:
    """3-way routing: decompose / execute_tool / retrieve."""
    route_dict = state.get("route_decision")
    if not route_dict:
        return "retrieve"

    route_decision = RouteDecision(**route_dict)

    # Tool execution takes priority over decomposition
    if route_decision.tool_decision and route_decision.tool_decision.requires_tool:
        return "execute_tool"

    if route_decision.requires_decomposition:
        return "decompose"

    return "retrieve"


def should_retry_route(state: AgentState) -> str:
    validation_dict = state.get("route_validation")
    if not validation_dict:
        return "continue"

    from app.schemas.planning import RouteValidationResult
    validation = RouteValidationResult(**validation_dict)

    retry_count = state.get("route_retry_count", 0)

    if validation.should_fallback:
        return "fallback"
    if validation.should_retry and retry_count < 1:
        return "retry"
    if validation.should_retry and retry_count >= 1:
        # Exhausted retries — fall back to heuristic
        return "fallback"
    return "continue"


def build_graph(nodes: GraphNodes) -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("llm_route_planner", llm_route_planner_node(nodes))
    workflow.add_node("route_validator", route_validator_node(nodes))
    workflow.add_node("heuristic_fallback", heuristic_fallback_node(nodes))
    workflow.add_node("decompose_router", decompose_router_node(nodes))
    workflow.add_node("task_decomposer", task_decomposer_node(nodes))
    workflow.add_node("decomposition_validator", decomposition_validator_node(nodes))
    workflow.add_node("tool_executor", tool_executor_node(nodes))
    workflow.add_node("retriever", retriever_node(nodes))
    workflow.add_node("coverage_checker", coverage_checker_node(nodes))
    workflow.add_node("evidence_selector", evidence_selector_node(nodes))
    workflow.add_node("reasoning", reasoning_node(nodes))
    workflow.add_node("answer_verifier", answer_verifier_node(nodes))

    workflow.set_entry_point("llm_route_planner")

    workflow.add_edge("llm_route_planner", "route_validator")

    # Route validator → retry/fallback/continue
    workflow.add_conditional_edges(
        "route_validator",
        should_retry_route,
        {
            "retry": "llm_route_planner",
            "fallback": "heuristic_fallback",
            "continue": "decompose_router",
        }
    )

    workflow.add_edge("heuristic_fallback", "decompose_router")

    # Decompose router → 3-way: decompose / execute_tool / retrieve
    workflow.add_conditional_edges(
        "decompose_router",
        should_route,
        {
            "decompose": "task_decomposer",
            "execute_tool": "tool_executor",
            "retrieve": "retriever",
        }
    )

    workflow.add_edge("task_decomposer", "decomposition_validator")
    workflow.add_edge("decomposition_validator", "retriever")

    # Tool executor → tool_mode_router: select (skip retrieval) or retrieve
    workflow.add_conditional_edges(
        "tool_executor",
        tool_mode_router,
        {
            "select": "evidence_selector",
            "retrieve": "retriever",
        }
    )

    workflow.add_edge("retriever", "coverage_checker")

    workflow.add_conditional_edges(
        "coverage_checker",
        lambda state: "retrieve" if state.get("needs_second_retrieval") else "select",
        {
            "retrieve": "retriever",
            "select": "evidence_selector"
        }
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
        use_llm_planner: bool = True
    ):
        self.nodes = GraphNodes(
            index_store=index_store,
            index_path=index_path,
            use_llm_planner=use_llm_planner
        )
        self.graph = build_graph(self.nodes)
    
    def is_ready(self) -> bool:
        return self.nodes.is_ready()
    
    def process_query(self, query: str, use_llm_planner: bool = True, conversation_id: Optional[str] = None, chat_history: Optional[list] = None) -> Dict[str, Any]:
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
            "conversation_id": final_state.get("conversation_id"),
        }
