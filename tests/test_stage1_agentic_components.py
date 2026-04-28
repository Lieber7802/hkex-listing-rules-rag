from app.schemas.query import PlannerOutput
from app.schemas.document import Chunk
from app.retrieval.hybrid_retriever import RetrievalResult
from app.agents.planner_agent import PlannerAgent
from app.agents.coverage_checker import CoverageChecker
from app.agents.evidence_selector import EvidenceSelector
from app.agents.answer_verifier import AnswerVerifier


def _result(chunk_id: str, text: str, score: float, rule_number: str | None = None) -> RetrievalResult:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        source_path="data/raw/test.md",
        text=text,
        rule_number=rule_number,
        section_title="Section",
    )
    return RetrievalResult(
        chunk_id=chunk_id,
        chunk=chunk,
        score=score,
        bm25_score=score,
        dense_score=score,
    )


def test_planner_output_contains_stage1_execution_fields():
    planner = PlannerAgent()
    output = planner.plan("Compare disclosure obligations and size test thresholds")

    assert isinstance(output, PlannerOutput)
    assert output.intent is not None
    assert isinstance(output.sub_tasks, list)
    assert output.retrieval_strategy in ["single_pass", "multi_query", "targeted_iterative"]
    assert isinstance(output.evidence_requirements, dict)
    assert output.answer_format in ["concise_with_citations", "comparison_table", "checklist_style"]


def test_coverage_checker_identifies_missing_subtasks():
    checker = CoverageChecker(min_support_score=0.6)
    plan = PlannerOutput(
        query_type="multi_hop",
        sub_queries=["disclosure obligations", "size test threshold"],
        needs_second_retrieval=True,
        reason="comparison",
        intent="comparison",
        sub_tasks=["disclosure obligations", "size test threshold"],
        retrieval_strategy="targeted_iterative",
        requires_tool=False,
        evidence_requirements={"disclosure obligations": "high", "size test threshold": "high"},
        answer_format="comparison_table",
    )
    results = [
        _result("c1", "Disclosure obligations under rule 14A.35", 0.9, "14A.35"),
    ]

    assessment = checker.assess(plan, results)

    assert assessment.needs_targeted_retrieval is True
    assert "size test threshold" in assessment.missing_information
    assert assessment.sub_task_coverage["disclosure obligations"] is True


def test_evidence_selector_prefers_rule_chunks_and_deduplicates():
    selector = EvidenceSelector(max_chunks=3)
    plan = PlannerOutput(
        query_type="direct",
        sub_queries=["what is rule 14A.35"],
        needs_second_retrieval=False,
        reason="lookup",
        intent="rule_lookup",
        sub_tasks=["rule lookup"],
        retrieval_strategy="single_pass",
        requires_tool=False,
        evidence_requirements={"rule lookup": "medium"},
        answer_format="concise_with_citations",
    )

    results = [
        _result("c1", "Rule 14A.35 disclosure requirement", 0.7, "14A.35"),
        _result("c2", "Rule 14A.36 announcement requirement", 0.65, "14A.36"),
        _result("c3", "General connected transaction guidance", 0.8, None),
        _result("c1", "Rule 14A.35 disclosure requirement", 0.6, "14A.35"),
    ]

    selected = selector.select(plan, results)

    selected_ids = [item.chunk_id for item in selected.selected_chunks]
    assert len(set(selected_ids)) == len(selected_ids)
    assert "c1" in selected_ids
    assert selected.diversity_score >= 0.0


def test_answer_verifier_flags_unsupported_claims():
    verifier = AnswerVerifier()
    answer = "Rule 14A.35 requires disclosure. Rule 99.99 mandates immediate suspension."
    results = [
        _result("c1", "Rule 14A.35 requires disclosure for connected transactions.", 0.9, "14A.35"),
    ]

    verification = verifier.verify(answer, results)

    assert verification.confidence_level in ["high", "medium", "low"]
    assert verification.revision_needed is True
    assert len(verification.unsupported_claims) >= 1
