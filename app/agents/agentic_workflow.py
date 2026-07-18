from __future__ import annotations

from typing import Dict, Any, Optional, Sequence
from pathlib import Path
import uuid
import math
import re

from langgraph.graph import StateGraph, END

from app.agents.graph_state import AgentState
from app.agents.planner_agent import PlannerAgent
from app.agents.reasoning_agent import ReasoningAgent
from app.agents.citation_formatter import CitationFormatter, format_citations
from app.agents.coverage_checker import CoverageChecker
from app.agents.evidence_selector import EvidenceSelector, select_evidence
from app.agents.answer_verifier import AnswerVerifier
from app.agents.query_rewriter import QueryRewriter
from app.agents.tool_input_extraction_node import tool_input_extraction_node, extract_tool_inputs
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import BaseEmbedder, get_embedder
from app.schemas.planning import RouteDecision, ToolDecision
from app.schemas.query import PlannerOutput
from app.schemas.citation import Citation
from app.tools.base_tool import ToolRegistry
from app.core.config import settings
from app.core.logger import logger


MAX_RETRIEVAL_ROUNDS = 2
MAX_RETRIEVED_CHUNKS_PER_ROUND = 10


class GraphNodes:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
        embedder: Optional[BaseEmbedder] = None,
        retriever: Optional[HybridRetriever] = None,
        use_llm_planner: bool = True,
        enable_tools: bool = True,
        enable_coverage_retry: bool = True,
        max_retrieval_rounds: int = MAX_RETRIEVAL_ROUNDS,
        evidence_selection_policy: str = "coverage_aware",
        tool_evidence_policy: str = "regulatory_grounded",
        answer_evidence_contract: str = "coverage_grounded",
        **kwargs,
    ):
        self.index_store = index_store
        self.index_path = index_path or settings.indexes_dir
        self.embedder = embedder
        self.retriever = retriever
        self.enable_tools = enable_tools
        self.enable_coverage_retry = enable_coverage_retry
        self.max_retrieval_rounds = max_retrieval_rounds
        self.evidence_selection_policy = evidence_selection_policy
        self.tool_evidence_policy = tool_evidence_policy
        self.answer_evidence_contract = answer_evidence_contract
        if self.index_store is None and self.retriever is not None:
            self.index_store = self.retriever.index_store
        self.planner = PlannerAgent(tool_evidence_policy=tool_evidence_policy)
        self.reasoning_agent = ReasoningAgent(
            answer_evidence_contract=answer_evidence_contract,
        )
        self.citation_formatter = CitationFormatter()
        self.coverage_checker = CoverageChecker()
        self.evidence_selector = EvidenceSelector(
            selection_policy=evidence_selection_policy,
        )
        self.answer_verifier = AnswerVerifier()
        self.tool_registry = ToolRegistry()

        if self.index_store is not None:
            if self.retriever is None:
                self.retriever = HybridRetriever(
                    index_store=self.index_store,
                    embedder=self.embedder or get_embedder(),
                )
        elif Path(self.index_path).exists():
            self._load_index_store()
        self._register_tools()

    def _load_index_store(self):
        try:
            self.index_store = IndexStore.load(self.index_path)
            self.retriever = HybridRetriever(
                index_store=self.index_store,
                embedder=self.embedder or get_embedder(),
            )
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
        if self.index_store is None or self.retriever is None:
            return False
        readiness_error = getattr(self.retriever, "readiness_error", None)
        return readiness_error is None or readiness_error() is None

    def readiness_error(self) -> Optional[str]:
        if self.index_store is None or self.retriever is None:
            return "retrieval index is not loaded"
        probe = getattr(self.retriever, "readiness_error", None)
        return probe() if probe is not None else None


def planner_agent_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        query = state["query"]
        use_llm = state.get("use_llm_planner", True)
        planner_output = nodes.planner.plan(query, use_llm=use_llm)
        fallback_used = "fallback" in (planner_output.reason or "").lower()

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
            fallback_used=fallback_used,
            sub_queries=list(planner_output.sub_queries),
        )

        logger.info(
            f"Planner: query_type={route_decision.query_type}, "
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
        retrieval_round = state.get("iteration_count", 0) + 1
        existing_ids = {chunk["chunk_id"] for chunk in state.get("retrieved_chunks", [])}

        original_query = None
        if retrieval_round == 1 and chat_history:
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
        queries_used = []
        if retrieval_round > 1:
            coverage = state.get("coverage_assessment") or {}
            retrieval_targets = (
                coverage.get("retrieval_targets")
                or coverage.get("missing_information", [])
            )
            targeted_queries = QueryRewriter().rewrite(query, retrieval_targets)
            queries_used = targeted_queries
            targeted_results = [
                nodes.retriever.retrieve(targeted_query)
                for targeted_query in targeted_queries
            ]
            unique_results = _round_robin_targeted_results(
                targeted_results,
                existing_ids,
                limit=MAX_RETRIEVED_CHUNKS_PER_ROUND,
            )
        else:
            if sub_queries and route_decision and route_decision.query_type == "multi_hop":
                queries_used = list(sub_queries)
                results = nodes.retriever.retrieve_for_sub_queries(sub_queries)

            if not results:
                queries_used = [query]
                results = nodes.retriever.retrieve(query)

            unique_results = _unique_results(results)

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
            for r in unique_results[:MAX_RETRIEVED_CHUNKS_PER_ROUND]
        ]

        logger.info(f"Retriever node: retrieved {len(chunks_data)} chunks")

        result = {
            "retrieved_chunks": chunks_data,
            "iteration_count": retrieval_round,
            "current_retrieval": {
                "round_number": retrieval_round,
                "queries": queries_used,
                "chunk_ids": [chunk["chunk_id"] for chunk in chunks_data],
                "coverage_before": (
                    state.get("coverage_assessment") or {}
                ).get("coverage_score", 0.0),
            },
        }
        if original_query:
            result["original_query"] = original_query
            result["query"] = query
        return result

    return node


def _unique_results(results: Sequence[RetrievalResult]) -> list[RetrievalResult]:
    """Keep ranked retrieval results unique while preserving their first occurrence."""
    unique_results: list[RetrievalResult] = []
    seen_ids: set[str] = set()
    for result in results:
        if result.chunk_id in seen_ids:
            continue
        seen_ids.add(result.chunk_id)
        unique_results.append(result)
    return unique_results


def _round_robin_targeted_results(
    targeted_results: Sequence[Sequence[RetrievalResult]],
    existing_ids: set[str],
    *,
    limit: int,
) -> list[RetrievalResult]:
    """Reserve a ranked unseen result for each targeted query before filling the cap.

    A second retrieval may contain several coverage gaps. Concatenating each query's
    top-k results lets the first gap consume the whole ten-chunk budget. Round-robin
    selection keeps one representative for every gap that has unseen evidence, then
    continues by rank until the per-round cap is reached.
    """
    per_target = [_unique_results(results) for results in targeted_results]
    positions = [0] * len(per_target)
    seen_ids = set(existing_ids)
    selected: list[RetrievalResult] = []

    while len(selected) < limit:
        selected_this_pass = False
        for index, candidates in enumerate(per_target):
            while positions[index] < len(candidates):
                candidate = candidates[positions[index]]
                positions[index] += 1
                if candidate.chunk_id in seen_ids:
                    continue
                seen_ids.add(candidate.chunk_id)
                selected.append(candidate)
                selected_this_pass = True
                break
            if len(selected) >= limit:
                break
        if not selected_this_pass:
            break

    return selected


def coverage_checker_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]

        if state.get("error") or not route_dict:
            return {"coverage_assessment": None, "needs_second_retrieval": False}

        route_decision = RouteDecision(**route_dict)

        if route_decision.tool_decision and route_decision.tool_decision.tool_mode == "tool_only":
            return {"coverage_assessment": None, "needs_second_retrieval": False}

        planner_output = route_decision.to_planner_output()
        results = _reconstruct_results(chunks_data, nodes.index_store)
        assessment = nodes.coverage_checker.assess(
            planner_output,
            results,
            intent=planner_output.intent,
        )
        retrieval_round = _complete_retrieval_round(
            state,
            coverage_after=assessment.coverage_score,
        )
        return {
            "coverage_assessment": assessment.model_dump(),
            "needs_second_retrieval": assessment.needs_targeted_retrieval,
            "retrieval_rounds": [retrieval_round] if retrieval_round else [],
        }

    return node


def evidence_selector_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        chunks_data = state["retrieved_chunks"]
        tool_results = state.get("tool_results", [])

        route_decision = RouteDecision(**route_dict) if route_dict else None
        planner_output = route_decision.to_planner_output() if route_decision else None

        results = _reconstruct_results(chunks_data, nodes.index_store)
        results = _merge_tool_evidence(results, tool_results, nodes.index_store)

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
        tool_results = state.get("tool_results", [])

        route_decision = RouteDecision(**route_dict) if route_dict else None
        planner_output = route_decision.to_planner_output() if route_decision else PlannerOutput(
            query_type="direct", sub_queries=[], intent="general"
        )

        results = _answer_evidence_results(state, nodes.index_store)

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

        results = _answer_evidence_results(state, nodes.index_store)

        if not results and tool_results:
            successful_tools = [r for r in tool_results if r.get("success")]
            if successful_tools:
                verification = _verify_tool_only_answer(answer, successful_tools)
                return {
                    "verification_result": verification,
                    "confidence_level": verification["confidence_level"],
                }

        verification = nodes.answer_verifier.verify(answer, results)
        verification_data = verification.model_dump()
        successful_tools = [r for r in tool_results if r.get("success")]
        if successful_tools:
            _merge_tool_output_verification(
                verification_data,
                _verify_tool_only_answer(answer, successful_tools),
            )
        return {
            "verification_result": verification_data,
            "confidence_level": verification_data["confidence_level"],
        }

    return node


_TOOL_FIELD_LABELS: Dict[str, tuple[str, ...]] = {
    "highest_ratio": ("highest ratio",),
    "suggested_classification": ("suggested classification", "classification"),
    "classification": ("transaction classification", "classification"),
    "display_name": ("transaction classification",),
    "shareholder_vote_required": ("shareholder vote", "shareholder approval"),
    "ifa_required": ("ifa", "independent financial adviser"),
    "circular_required": ("circular required", "circular requirement"),
    "announcement_deadline_days": ("announcement deadline",),
}
_CLASSIFICATION_TERMS = (
    "de minimis",
    "share transaction",
    "discloseable transaction",
    "major transaction",
    "very substantial",
)


def _verify_tool_only_answer(
    answer: str,
    successful_tools: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify that a tool-only answer does not contradict structured tool output.

    Tool execution proves that a calculation or classification completed; it does
    not prove that the generated prose repeated the result faithfully. This check
    deliberately looks only for explicit, labelled conflicts, so a concise answer
    that omits a tool field remains valid while a conflicting field is rejected.
    """
    contradictions: list[Dict[str, str]] = []
    for tool_result in successful_tools:
        output = tool_result.get("output")
        if not isinstance(output, dict):
            continue
        tool_name = str(tool_result.get("tool_name") or "unknown_tool")
        contradictions.extend(
            _tool_output_contradictions(answer, output, tool_name)
        )

    is_supported = not contradictions
    if is_supported:
        summary = (
            "Answer is consistent with tool execution "
            f"({len(successful_tools)} tool(s) executed successfully)."
        )
    else:
        summary = "Answer contradicts one or more successful tool outputs."

    return {
        "is_supported": is_supported,
        "unsupported_claims": [item["description"] for item in contradictions],
        "contradictions": contradictions,
        "confidence_level": "high" if is_supported else "low",
        "revision_needed": not is_supported,
        "summary": summary,
    }


def _merge_tool_output_verification(
    verification: Dict[str, Any],
    tool_verification: Dict[str, Any],
) -> None:
    """Make successful tool output an additional verifier for mixed tool/RAG paths."""
    if tool_verification["is_supported"]:
        return

    verification["unsupported_claims"] = list(dict.fromkeys([
        *verification.get("unsupported_claims", []),
        *tool_verification["unsupported_claims"],
    ]))
    verification["contradictions"] = [
        *verification.get("contradictions", []),
        *tool_verification["contradictions"],
    ]
    verification["confidence_level"] = "low"
    verification["revision_needed"] = True
    verification["is_supported"] = False


def _tool_output_contradictions(
    answer: str,
    output: Dict[str, Any],
    tool_name: str,
) -> list[Dict[str, str]]:
    contradictions: list[Dict[str, str]] = []
    answer_lower = answer.lower()

    for field, expected in _tool_scalar_facts(output):
        labels = _tool_labels_for_field(field)
        if not labels:
            continue

        actual_number = _labelled_number(answer_lower, labels)
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            if actual_number is not None and not math.isclose(
                actual_number,
                float(expected),
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                contradictions.append(_tool_contradiction(
                    tool_name,
                    field,
                    expected,
                    actual_number,
                ))
            continue

        if isinstance(expected, bool):
            actual_boolean = _labelled_boolean(answer_lower, labels)
            if actual_boolean is not None and actual_boolean != expected:
                contradictions.append(_tool_contradiction(
                    tool_name,
                    field,
                    expected,
                    actual_boolean,
                ))
            continue

        if field in {"classification", "suggested_classification", "display_name"}:
            expected_classification = _canonical_classification(str(expected))
            mentioned_classifications = {
                term for term in _CLASSIFICATION_TERMS
                if term in answer_lower
            }
            if (
                expected_classification
                and mentioned_classifications
                and expected_classification not in mentioned_classifications
            ):
                contradictions.append(_tool_contradiction(
                    tool_name,
                    field,
                    expected_classification,
                    sorted(mentioned_classifications),
                ))

    return contradictions


def _tool_scalar_facts(output: Dict[str, Any]) -> list[tuple[str, Any]]:
    """Expose the scalar conclusion fields that a tool-only answer can state."""
    facts: list[tuple[str, Any]] = []
    for field, value in output.items():
        if field == "ratios" and isinstance(value, dict):
            facts.extend((ratio_name, ratio_value) for ratio_name, ratio_value in value.items()
                         if isinstance(ratio_value, (str, int, float, bool)))
        elif isinstance(value, (str, int, float, bool)):
            facts.append((field, value))
    return facts


def _tool_labels_for_field(field: str) -> tuple[str, ...]:
    if field in _TOOL_FIELD_LABELS:
        return _TOOL_FIELD_LABELS[field]
    if field.endswith("_ratio"):
        return (field.replace("_", " "),)
    return ()


def _labelled_number(answer: str, labels: Sequence[str]) -> Optional[float]:
    for label in labels:
        label_pattern = re.escape(label).replace(r"\ ", r"\s+")
        pattern = (
            rf"\b{label_pattern}\b"
            r"(?:\s*(?:is|was|equals?|of))?\s*[:=\-]?\s*"
            r"(\d+(?:\.\d+)?)"
        )
        match = re.search(pattern, answer, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _labelled_boolean(answer: str, labels: Sequence[str]) -> Optional[bool]:
    for label in labels:
        label_pattern = re.escape(label).replace(r"\ ", r"\s+")
        match = re.search(
            rf"\b{label_pattern}\b(?P<tail>.{{0,48}})",
            answer,
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        tail = match.group("tail").lower()
        if re.search(r"\b(no|false|not required|not needed|not necessary)\b", tail):
            return False
        if re.search(r"\b(yes|true|required|must)\b", tail):
            return True
    return None


def _canonical_classification(value: str) -> Optional[str]:
    normalized = re.sub(r"[_\-]+", " ", value.lower())
    for term in _CLASSIFICATION_TERMS:
        if term in normalized:
            return term
    return None


def _tool_contradiction(
    tool_name: str,
    field: str,
    expected: Any,
    actual: Any,
) -> Dict[str, str]:
    description = (
        f"Tool {tool_name} returned {field}={expected!r}, "
        f"but the answer states {actual!r}."
    )
    return {
        "claim": field,
        "chunk_a_id": f"tool:{tool_name}",
        "chunk_b_id": "answer",
        "description": description,
        "contradiction_type": "tool_output",
    }


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


def _answer_evidence_results(state: AgentState, index_store: Optional[IndexStore]):
    selected_evidence = state.get("selected_evidence")
    if selected_evidence is not None:
        return _reconstruct_results(
            selected_evidence.get("selected_chunks", []),
            index_store,
        )
    results = _reconstruct_results(state.get("retrieved_chunks", []), index_store)
    return _merge_tool_evidence(results, state.get("tool_results", []), index_store)


def _merge_tool_evidence(
    results: list[RetrievalResult], tool_results: list[Dict[str, Any]],
    index_store: Optional[IndexStore],
) -> list[RetrievalResult]:
    """Treat rule-lookup output as normal evidence throughout the pipeline."""
    if index_store is None:
        return results
    merged = {result.chunk_id: result for result in results}
    for tool_result in tool_results:
        if not tool_result.get("success") or tool_result.get("tool_name") != "rule_lookup":
            continue
        output = tool_result.get("output") or {}
        for chunk_data in output.get("chunks", []):
            chunk_id = chunk_data.get("chunk_id")
            chunk = index_store.get_chunk_by_id(chunk_id) if chunk_id else None
            if chunk and chunk_id not in merged:
                merged[chunk_id] = RetrievalResult(
                    chunk_id=chunk_id, chunk=chunk, score=1.0,
                    bm25_score=1.0, dense_score=1.0,
                )
    return list(merged.values())


def _complete_retrieval_round(
    state: AgentState,
    coverage_after: float,
) -> Optional[Dict[str, Any]]:
    current_retrieval = state.get("current_retrieval")
    if not current_retrieval:
        return None
    return {
        **current_retrieval,
        "coverage_after": coverage_after,
    }


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
                        return _tool_execution_result(**{
                            "call_id": call_id, "tool_name": tool_name,
                            "success": True, "output": output, "error": None,
                            "_recovered": True,
                        })
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
        return _tool_execution_result(**{
            "call_id": call_id, "tool_name": tool_name,
            "success": True, "output": output, "error": None,
        })
    except Exception as e:
        return {
            "call_id": call_id, "tool_name": tool_name,
            "success": False, "output": None,
            "error": f"Tool execution error: {str(e)}",
        }


def _tool_execution_result(**result: Any) -> Dict[str, Any]:
    """Normalize domain failures returned as ``{'error': ...}`` by tools."""
    output = result.get("output")
    if isinstance(output, dict) and output.get("error"):
        result["success"] = False
        result["error"] = str(output["error"])
    return result


def _tool_chain_context(inputs: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Preserve query facts that downstream chain steps require."""
    context = dict(inputs)
    lowered = query.lower()
    if "is_connected" not in context:
        context["is_connected"] = (
            "connected transaction" in lowered or "connected party" in lowered
            or "\u5173\u8054\u4ea4\u6613" in query
        )
    if context["is_connected"] and "connected_party_type" not in context:
        if "director" in lowered or "\u8463\u4e8b" in query:
            context["connected_party_type"] = "director"
        elif "substantial shareholder" in lowered or "\u5927\u80a1\u4e1c" in query:
            context["connected_party_type"] = "substantial_shareholder"
    if "transaction_type" not in context:
        context["transaction_type"] = "disposal" if "disposal" in lowered else "acquisition"
    return context


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
        if not tool_name:
            logger.warning("Tool execution skipped because the route has no tool name")
            return {"tool_calls": [], "tool_results": []}
        tool_inputs = dict(tool_decision.tool_inputs_hint) if tool_decision.tool_inputs_hint else {}

        all_tool_calls = []
        all_tool_results = []
        query_text = state.get("query", "") or state.get("original_query", "")
        user_context = _tool_chain_context(tool_inputs, query_text)

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
    if (
        route_decision.tool_decision
        and route_decision.tool_decision.requires_tool
        and state.get("enable_tools", True)
    ):
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

    workflow.add_node("planner_agent", planner_agent_node(nodes))
    workflow.add_node("tool_input_extraction", tool_input_extraction_node(nodes))
    workflow.add_node("tool_executor", tool_executor_node(nodes))
    workflow.add_node("retriever", retriever_node(nodes))
    workflow.add_node("coverage_checker", coverage_checker_node(nodes))
    workflow.add_node("evidence_selector", evidence_selector_node(nodes))
    workflow.add_node("reasoning", reasoning_node(nodes))
    workflow.add_node("answer_verifier", answer_verifier_node(nodes))

    workflow.set_entry_point("planner_agent")

    workflow.add_conditional_edges(
        "planner_agent",
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
            and nodes.enable_coverage_retry
            and state.get("iteration_count", 0) < nodes.max_retrieval_rounds
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


class AgenticRAGOrchestrator:
    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
        embedder: Optional[BaseEmbedder] = None,
        retriever: Optional[HybridRetriever] = None,
        use_llm_planner: bool = True,
        enable_tools: bool = True,
        enable_coverage_retry: bool = True,
        max_retrieval_rounds: int = MAX_RETRIEVAL_ROUNDS,
        evidence_selection_policy: str = "coverage_aware",
        tool_evidence_policy: str = "regulatory_grounded",
        answer_evidence_contract: str = "coverage_grounded",
    ):
        self.nodes = GraphNodes(
            index_store=index_store,
            index_path=index_path,
            embedder=embedder,
            retriever=retriever,
            enable_tools=enable_tools,
            enable_coverage_retry=enable_coverage_retry,
            max_retrieval_rounds=max_retrieval_rounds,
            evidence_selection_policy=evidence_selection_policy,
            tool_evidence_policy=tool_evidence_policy,
            answer_evidence_contract=answer_evidence_contract,
        )
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
            "current_retrieval": None,
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
            "enable_tools": self.nodes.enable_tools,
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
