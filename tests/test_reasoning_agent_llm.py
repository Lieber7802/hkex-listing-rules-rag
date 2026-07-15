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
