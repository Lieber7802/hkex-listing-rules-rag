from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.reasoning_agent import ReasoningAgent
from app.retrieval.hybrid_retriever import RetrievalResult
from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput


def test_reasoning_uses_the_shared_client_for_llm_generation():
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Model answer"))]
    )
    agent = ReasoningAgent(llm_provider="openai")
    agent._get_client = MagicMock(return_value=client)
    chunk = Chunk(chunk_id="c1", document_id="d1", source_path="rules.md", text="Evidence")
    output = agent.reason(
        "Question", PlannerOutput(query_type="direct", sub_queries=["Question"]),
        [RetrievalResult("c1", chunk, 1.0, 1.0, 1.0)],
    )
    assert output.answer == "Model answer"
    client.chat.completions.create.assert_called_once()


def test_empty_llm_content_falls_back_to_tool_and_regulatory_evidence():
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )
    agent = ReasoningAgent(llm_provider="openai", answer_evidence_contract="coverage_grounded")
    agent._get_client = MagicMock(return_value=client)
    chunk = Chunk(
        chunk_id="c1", document_id="d1", source_path="rules.md",
        text="Rule 14.34 requires an announcement.", rule_number="14.34",
    )
    plan = PlannerOutput(
        query_type="direct", sub_queries=["Question"], intent="calculation_required",
        tool_mode="tool_plus_retrieval",
    )

    output = agent.reason(
        "Question", plan, [RetrievalResult("c1", chunk, 1.0, 1.0, 1.0)],
        tool_results=[{
            "tool_name": "transaction_classifier",
            "success": True,
            "output": {"classification": "share_transaction"},
        }],
    )

    assert "Tool conclusion" in output.answer
    assert "Regulatory basis" in output.answer
