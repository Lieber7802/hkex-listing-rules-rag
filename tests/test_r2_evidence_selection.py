import numpy as np

from app.agents.agentic_workflow import AgenticRAGOrchestrator
from app.agents.evidence_selector import EvidenceSelector
from app.retrieval.index_store import IndexStore
from app.retrieval.hybrid_retriever import RetrievalResult
from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput


def _result(chunk_id: str, text: str, score: float, rule_number: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        chunk=Chunk(
            chunk_id=chunk_id,
            document_id="rule-document",
            source_path="data/raw/rules.md",
            text=text,
            rule_number=rule_number,
            section_title=text.split(".")[0],
        ),
        score=score,
        bm25_score=score,
        dense_score=score,
    )


def _complex_plan() -> PlannerOutput:
    return PlannerOutput(
        query_type="multi_hop",
        sub_queries=["announcement requirement", "shareholder approval"],
        intent="comparison",
        sub_tasks=["announcement requirement", "shareholder approval"],
        evidence_requirements={
            "announcement requirement": "high",
            "shareholder approval": "high",
        },
        retrieval_strategy="targeted_iterative",
        answer_format="comparison_table",
    )


def test_coverage_aware_selection_reserves_evidence_for_each_subtask():
    results = [
        _result(
            f"announcement-{index}",
            "Announcement requirement for a notifiable transaction.",
            1.0 - index / 100,
            f"14.{30 + index}",
        )
        for index in range(8)
    ]
    results.append(_result(
        "approval",
        "Shareholder approval is required for a major transaction.",
        0.20,
        "14.49",
    ))

    selected = EvidenceSelector(selection_policy="coverage_aware").select(
        _complex_plan(), results
    )

    selected_ids = {item.chunk_id for item in selected.selected_chunks}
    assert "approval" in selected_ids
    assert selected.covered_subtasks == [
        "announcement requirement",
        "shareholder approval",
    ]
    assert selected.uncovered_subtasks == []
    assert selected.selection_budget == 8


def test_coverage_aware_selection_keeps_simple_queries_within_five_chunks():
    plan = PlannerOutput(
        query_type="direct",
        sub_queries=["announcement requirement"],
        intent="rule_lookup",
        sub_tasks=["announcement requirement"],
        evidence_requirements={"announcement requirement": "medium"},
    )
    results = [
        _result(
            f"chunk-{index}",
            "Announcement requirement for listed issuers.",
            1.0 - index / 100,
            f"14.{index}",
        )
        for index in range(7)
    ]

    selected = EvidenceSelector(selection_policy="coverage_aware").select(plan, results)

    assert len(selected.selected_chunks) == 5
    assert selected.selection_budget == 5


def test_coverage_selection_does_not_treat_generic_prompt_words_as_evidence():
    plan = PlannerOutput(
        query_type="multi_hop",
        sub_queries=["identify the grounded relationship"],
        intent="comparison",
        sub_tasks=["identify the grounded relationship"],
        evidence_requirements={"identify the grounded relationship": "high"},
    )
    results = [
        _result(
            "generic",
            "This evidence passage discusses a grounded relationship in general terms.",
            0.99,
            "14.01",
        ),
        _result(
            "specific",
            "Shareholder approval is required for a major transaction.",
            0.20,
            "14.49",
        ),
    ]

    selected = EvidenceSelector(selection_policy="coverage_aware").select(plan, results)

    assert selected.covered_subtasks == []
    assert selected.uncovered_subtasks == ["identify the grounded relationship"]


def test_coverage_selection_recognizes_chinese_no_space_rule_reference():
    task = "\u8bf7\u8bf4\u660e\u7b2c14A.35\u6761\u7684\u62ab\u9732\u8981\u6c42"
    plan = PlannerOutput(
        query_type="direct",
        sub_queries=[task],
        intent="rule_lookup",
        sub_tasks=[task],
        evidence_requirements={task: "medium"},
    )
    results = [
        _result(
            "wrong-rule",
            "Disclosure requirements for a connected transaction.",
            0.95,
            "14A.36",
        ),
        _result(
            "requested-rule",
            "Rule 14A.35 sets the disclosure requirement.",
            0.20,
            "14A.35",
        ),
    ]

    selected = EvidenceSelector(selection_policy="coverage_aware").select(plan, results)

    assert selected.selected_chunks[0].chunk_id == "requested-rule"
    assert selected.covered_subtasks == [task]


class _StaticRetriever:
    def __init__(self, results: list[RetrievalResult]):
        self.results = results

    def retrieve(self, query: str) -> list[RetrievalResult]:
        return self.results

    def retrieve_for_sub_queries(self, queries: list[str]) -> list[RetrievalResult]:
        return self.results


def test_workflow_records_coverage_selection_diagnostics():
    chunks = [
        result.chunk
        for result in [
            _result(
                f"announcement-{index}",
                "Announcement requirement for a notifiable transaction.",
                1.0 - index / 100,
                f"14.{30 + index}",
            )
            for index in range(8)
        ] + [
            _result(
                "approval",
                "Shareholder approval is required for a major transaction.",
                0.20,
                "14.49",
            )
        ]
    ]
    store = IndexStore()
    store.build_indexes(chunks, np.ones((len(chunks), 4), dtype=np.float32))
    results = [
        RetrievalResult(
            chunk_id=chunk.chunk_id,
            chunk=chunk,
            score=1.0 - index / 100,
            bm25_score=1.0,
            dense_score=1.0,
        )
        for index, chunk in enumerate(chunks)
    ]
    orchestrator = AgenticRAGOrchestrator(
        index_store=store,
        retriever=_StaticRetriever(results),
        use_llm_planner=False,
        evidence_selection_policy="coverage_aware",
    )

    result = orchestrator.process_query(
        "Compare announcement requirement and shareholder approval",
        use_llm_planner=False,
    )

    diagnostics = result["selected_evidence"]
    assert diagnostics["selection_budget"] == 8
    assert "approval" in {item["chunk_id"] for item in diagnostics["selected_chunks"]}
    assert diagnostics["covered_subtasks"]
