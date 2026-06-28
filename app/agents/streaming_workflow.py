"""Streaming wrapper around LangGraph workflow.

Uses graph.stream() to yield state updates after each node execution,
converting them to SSE events.
"""

import time
import json
from typing import Generator, Dict, Any, Optional
from pathlib import Path

from app.agents.langgraph_workflow_v2 import GraphNodes, build_graph, AgentState
from app.schemas.planning import RouteDecision
from app.retrieval.index_store import IndexStore
from app.core.config import settings
from app.core.logger import logger


# Map LangGraph node names → SSE event types
NODE_TO_EVENT = {
    "planner_agent_v2": "routing_complete",
    "tool_input_extraction": None,  # skip — internal node
    "tool_executor": "tool_executed",
    "retriever": "retrieval_complete",
    "coverage_checker": "coverage_checked",
    "evidence_selector": "evidence_selected",
    "reasoning": "answer_chunk",
    "answer_verifier": "verification_complete",
}


class StreamingOrchestrator:
    """Wraps the LangGraph workflow to emit SSE events."""

    def __init__(
        self,
        index_store: Optional[IndexStore] = None,
        index_path: Optional[Path] = None,
    ):
        self.nodes = GraphNodes(
            index_store=index_store,
            index_path=index_path,
        )
        self.graph = build_graph(self.nodes)

    def is_ready(self) -> bool:
        return self.nodes.is_ready()

    def stream_query(self, query: str, use_llm_planner: bool = True, conversation_id: Optional[str] = None, chat_history: Optional[list] = None) -> Generator[Dict[str, Any], None, None]:
        """Generator that yields SSE event dicts as the graph executes.

        Yields:
            Dict with keys: event (str), data (dict)
        """
        start_time = time.time()

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

        tools_executed = 0

        try:
            # graph.stream() yields dict of {node_name: state_update}
            for step in self.graph.stream(initial_state):
                for node_name, state_update in step.items():
                    event_type = NODE_TO_EVENT.get(node_name, "node_complete")

                    # Skip pass-through nodes
                    if event_type is None:
                        continue

                    # Special handling for tool_executor
                    if node_name == "tool_executor":
                        tool_results = state_update.get("tool_results", [])
                        tools_executed += len(tool_results)
                        for tr in tool_results:
                            yield {
                                "event": "tool_executed",
                                "data": {
                                    "tool_name": tr.get("tool_name"),
                                    "success": tr.get("success"),
                                    "output_preview": self._preview(tr.get("output")),
                                }
                            }
                        continue

                    # Special handling for reasoning (answer + citations)
                    if node_name == "reasoning":
                        yield {"event": "reasoning_started", "data": {}}
                        answer = state_update.get("answer", "")
                        if answer:
                            for chunk in self._chunk_answer(answer):
                                yield {"event": "answer_chunk", "data": {"content": chunk}}
                        citations = state_update.get("citations", [])
                        if citations:
                            yield {
                                "event": "citations",
                                "data": {"citations": [self._serialize_citation(c) for c in citations]},
                            }
                        continue

                    # Generic event
                    event_data = self._build_event_data(node_name, state_update)
                    yield {"event": event_type, "data": event_data}

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {"event": "error", "data": {"message": str(e)}}

        # Final done event
        elapsed_ms = int((time.time() - start_time) * 1000)
        yield {
            "event": "done",
            "data": {
                "total_time_ms": elapsed_ms,
                "tools_executed": tools_executed,
            }
        }

    def _build_event_data(self, node_name: str, state_update: Dict[str, Any]) -> Dict[str, Any]:
        """Build event-specific data payload."""
        if node_name == "planner_agent_v2":
            return {
                "query_type": state_update.get("query_type"),
                "route_summary": self._summarize_route(state_update.get("route_decision")),
            }

        if node_name == "retriever":
            chunks = state_update.get("retrieved_chunks", [])
            top_score = max((c.get("score", 0) for c in chunks), default=0)
            return {"num_chunks": len(chunks), "top_score": round(top_score, 3)}

        if node_name == "answer_verifier":
            return {
                "confidence_level": state_update.get("confidence_level"),
            }

        return {}

    @staticmethod
    def _summarize_route(route_dict: Optional[Dict]) -> Optional[str]:
        if not route_dict:
            return None
        return f"{route_dict.get('query_type')}/{route_dict.get('intent')}"

    @staticmethod
    def _preview(output: Any, max_len: int = 200) -> Optional[str]:
        if output is None:
            return None
        text = json.dumps(output, ensure_ascii=False)
        return text[:max_len] + ("..." if len(text) > max_len else "")

    @staticmethod
    def _serialize_citation(c) -> Dict[str, Any]:
        if hasattr(c, "model_dump"):
            return c.model_dump()
        if isinstance(c, dict):
            return c
        return dict(c)

    @staticmethod
    def _chunk_answer(answer: str, chunk_size: int = 100) -> list:
        """Split answer into chunks for streaming delivery."""
        if len(answer) <= chunk_size:
            return [answer]
        return [answer[i:i + chunk_size] for i in range(0, len(answer), chunk_size)]
