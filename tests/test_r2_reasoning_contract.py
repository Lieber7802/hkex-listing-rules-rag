from app.agents.reasoning_agent import ReasoningAgent
from app.retrieval.hybrid_retriever import RetrievalResult
from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput


def _result(chunk_id: str, rule_number: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        chunk=Chunk(
            chunk_id=chunk_id,
            document_id="rule-document",
            source_path="data/raw/rules.md",
            rule_number=rule_number,
            section_title="HKEX requirement",
            text=text,
        ),
        score=1.0,
        bm25_score=1.0,
        dense_score=1.0,
    )


def test_grounded_contract_fallback_addresses_each_selected_subtask():
    agent = ReasoningAgent(answer_evidence_contract="coverage_grounded")
    agent._get_client = lambda: None
    plan = PlannerOutput(
        query_type="multi_hop",
        sub_queries=["announcement", "shareholder approval"],
        sub_tasks=["announcement", "shareholder approval"],
        intent="comparison",
        answer_format="comparison_table",
    )

    output = agent.reason(
        "Compare announcement and shareholder approval requirements.",
        plan,
        [
            _result("announcement", "14.34", "Rule 14.34 requires an announcement."),
            _result("approval", "14.49", "Rule 14.49 requires shareholder approval."),
        ],
    )

    assert "Rule 14.34" in output.answer
    assert "Rule 14.49" in output.answer
    assert output.used_chunk_ids == ["announcement", "approval"]


def test_grounded_contract_combines_tool_conclusion_with_regulatory_basis():
    agent = ReasoningAgent(answer_evidence_contract="coverage_grounded")
    agent._get_client = lambda: None
    plan = PlannerOutput(
        query_type="direct",
        sub_queries=["disclosure consequence"],
        sub_tasks=["disclosure consequence"],
        intent="calculation_required",
        requires_tool=True,
        tool_name="transaction_classifier",
        tool_mode="tool_plus_retrieval",
    )

    output = agent.reason(
        "What disclosure follows from this classification?",
        plan,
        [_result("disclosure", "14.34", "Rule 14.34 requires an announcement for this transaction.")],
        tool_results=[{
            "tool_name": "transaction_classifier",
            "success": True,
            "output": {
                "classification": "major_transaction",
                "display_name": "Major Transaction",
                "applicable_rules": ["14.34"],
            },
        }],
    )

    assert "Tool conclusion" in output.answer
    assert "Regulatory basis" in output.answer
    assert "Practical consequence" in output.answer
    assert "Rule 14.34" in output.answer
