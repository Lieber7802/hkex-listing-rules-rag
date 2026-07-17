from __future__ import annotations

import time
import uuid
from typing import Callable, List, Optional, Sequence

from app.agents.agentic_workflow import AgenticRAGOrchestrator
from app.evaluation.runners.base import ExperimentConfig
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow, RowType


class AgenticRAGRunner:
    def __init__(
        self, config: ExperimentConfig,
        orchestrator_factory: Optional[Callable[..., AgenticRAGOrchestrator]] = None,
    ) -> None:
        self.config = config
        self._factory = orchestrator_factory or AgenticRAGOrchestrator

    def _orchestrator(self) -> AgenticRAGOrchestrator:
        return self._factory(
            use_llm_planner=self.config.planner_mode == "llm_primary",
            enable_tools=self.config.enable_tools,
            enable_coverage_retry=self.config.enable_coverage_retry,
            max_retrieval_rounds=self.config.max_retrieval_rounds,
            evidence_selection_policy=self.config.evidence_selection_policy,
            tool_evidence_policy=self.config.tool_evidence_policy,
            answer_evidence_contract=self.config.answer_evidence_contract,
        )

    def run_case(self, case: BenchmarkCase, run_id: str) -> Sequence[EvaluationRunRow]:
        orchestrator = self._orchestrator()
        conversation_id = str(uuid.uuid4()) if case.turns else None
        history: List[dict] = []
        rows: List[EvaluationRunRow] = []
        turns = case.turns or []
        queries = [turn.query for turn in turns] if turns else [case.query or ""]
        last_result = None

        for index, query in enumerate(queries, start=1):
            started = time.perf_counter()
            try:
                result = orchestrator.process_query(
                    query,
                    use_llm_planner=self.config.planner_mode == "llm_primary",
                    conversation_id=conversation_id,
                    chat_history=history or None,
                )
                error = result.get("error")
            except Exception as exc:  # A failed case is an auditable result, not a dropped row.
                result, error = {}, str(exc)
            latency = time.perf_counter() - started
            answer = result.get("answer", "")
            history.extend(({"role": "user", "content": query}, {"role": "assistant", "content": answer}))
            last_result = result
            if turns:
                rows.append(self._row(
                    run_id, case.case_id, query, result, latency, error,
                    RowType.TURN, turn_index=index, conversation_id=conversation_id,
                ))

        assert last_result is not None
        row_type = RowType.AGGREGATE if turns else RowType.SINGLE_TURN
        rows.append(self._row(
            run_id, case.case_id, queries[-1], last_result, latency, error,
            row_type, conversation_id=conversation_id,
        ))
        return rows

    def _row(self, run_id, case_id, query, result, latency, error, row_type, **extra):
        rounds = result.get("retrieval_rounds", [])
        coverage = result.get("coverage_assessment") or {}
        return EvaluationRunRow(
            run_id=run_id, case_id=case_id, system=self.config.system_id,
            row_type=row_type, query=query, answer=result.get("answer", ""),
            retrieved_chunks=result.get("retrieved_chunks", []),
            selected_evidence=result.get("selected_evidence"),
            citations=[c.model_dump() if hasattr(c, "model_dump") else c for c in result.get("citations", [])],
            route_decision=result.get("route_decision"), tool_calls=result.get("tool_calls", []),
            tool_results=result.get("tool_results", []), verification_result=result.get("verification_result"),
            retrieval_rounds=rounds, coverage_before=(rounds[0].get("coverage_before") if rounds else None),
            coverage_after=coverage.get("coverage_score"), answer_before_verification=result.get("answer"),
            answer_after_verification=result.get("answer"), latency_seconds=latency, error=error,
            **extra,
        )
