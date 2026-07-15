from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import List, Optional, Sequence

from app.agents.reasoning_agent import ReasoningAgent
from app.evaluation.runners.base import ExperimentConfig
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow, RowType
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.index_store import IndexStore
from app.schemas.query import PlannerOutput
from app.agents.citation_formatter import format_citations


class TraditionalHybridRAGRunner:
    """B3 baseline: one hybrid retrieval pass and the shared answer generator."""

    def __init__(
        self, config: ExperimentConfig, retriever: Optional[HybridRetriever] = None,
        reasoning_agent: Optional[ReasoningAgent] = None, index_path: Optional[Path] = None,
    ) -> None:
        self.config = config
        self._retriever = retriever
        self._reasoning = reasoning_agent or ReasoningAgent()
        self._index_path = index_path

    def _get_retriever(self) -> HybridRetriever:
        if self._retriever is None:
            if self._index_path is not None:
                self._retriever = HybridRetriever(IndexStore.load(self._index_path))
            else:
                self._retriever = HybridRetriever(
                    IndexStore.load(__import__("app.core.config", fromlist=["settings"]).settings.indexes_dir)
                )
        return self._retriever

    def run_case(self, case: BenchmarkCase, run_id: str) -> Sequence[EvaluationRunRow]:
        history: List[dict] = []
        conversation_id = str(uuid.uuid4()) if case.turns else None
        rows: List[EvaluationRunRow] = []
        queries = [turn.query for turn in case.turns] if case.turns else [case.query or ""]
        last = None
        for index, query in enumerate(queries, start=1):
            started = time.perf_counter()
            results, answer, error = [], "", None
            try:
                results = self._get_retriever().retrieve(query)
                output = self._reasoning.reason(
                    query, PlannerOutput(query_type="direct", sub_queries=[query], intent="general"),
                    results, chat_history=history or None,
                )
                answer = output.answer
                citations = format_citations([r for r in results if r.chunk_id in output.used_chunk_ids])
            except Exception as exc:
                citations, error = [], str(exc)
            latency = time.perf_counter() - started
            payload = {"results": results, "answer": answer, "citations": citations, "error": error, "latency": latency}
            history.extend(({"role": "user", "content": query}, {"role": "assistant", "content": answer}))
            last = payload
            if case.turns:
                rows.append(self._row(run_id, case.case_id, query, payload, RowType.TURN, index, conversation_id))
        assert last is not None
        rows.append(self._row(run_id, case.case_id, queries[-1], last, RowType.AGGREGATE if case.turns else RowType.SINGLE_TURN, None, conversation_id))
        return rows

    def _row(self, run_id, case_id, query, payload, row_type, turn_index, conversation_id):
        return EvaluationRunRow(
            run_id=run_id, case_id=case_id, system=self.config.system_id, row_type=row_type,
            query=query, answer=payload["answer"], turn_index=turn_index, conversation_id=conversation_id,
            retrieved_chunks=[{
                "chunk_id": r.chunk_id, "rule_number": r.chunk.rule_number,
                "source_path": r.chunk.source_path, "score": r.score,
                "bm25_score": r.bm25_score, "dense_score": r.dense_score,
            } for r in payload["results"]],
            citations=[c.model_dump() if hasattr(c, "model_dump") else c for c in payload["citations"]],
            answer_before_verification=payload["answer"], answer_after_verification=payload["answer"],
            latency_seconds=payload["latency"], error=payload["error"],
        )
