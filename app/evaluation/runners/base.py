from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow


@dataclass(frozen=True)
class ExperimentConfig:
    """Immutable system definition recorded alongside every evaluation run."""

    system_id: str
    system_label: str
    planner_mode: str
    enable_tools: bool
    enable_coverage_retry: bool
    max_retrieval_rounds: int


SYSTEM_CONFIGS = {
    "B3": ExperimentConfig("B3", "traditional_hybrid_rag", "none", False, False, 1),
    "A1": ExperimentConfig("A1", "agentic_rag", "llm_primary", True, True, 2),
    "A2": ExperimentConfig("A2", "agentic_no_coverage_retry", "llm_primary", True, False, 1),
    "A3": ExperimentConfig("A3", "agentic_no_tools", "llm_primary", False, True, 2),
}


class EvaluationSystem(Protocol):
    config: ExperimentConfig

    def run_case(self, case: BenchmarkCase, run_id: str) -> Sequence[EvaluationRunRow]:
        """Run one benchmark case and return turn rows plus one case-level row."""
