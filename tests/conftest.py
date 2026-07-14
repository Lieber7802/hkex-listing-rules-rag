import pytest
import numpy as np


class DeterministicTestEmbedder:
    def embed_single(self, text: str) -> np.ndarray:
        vector = np.zeros(384, dtype=np.float32)
        vector[0] = 1.0
        return vector


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch, tmp_path):
    """Ensure tests never reach out to Ollama or external LLM APIs.

    API keys are stripped, the default index path is redirected to a temporary
    directory, and workflow embedders are deterministic. This keeps tests on
    heuristic/template paths unless they explicitly inject local dependencies.

    We patch both environment variables AND the settings singleton,
    because pydantic-settings reads from .env at import time.
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "indexes_dir", tmp_path / "indexes")
    monkeypatch.setattr(settings, "session_storage_dir", tmp_path / "sessions")

    from app.agents import agentic_workflow
    from app.api import chat as chat_api
    from app.api import chat_stream as chat_stream_api
    from app.retrieval import hybrid_retriever

    monkeypatch.setattr(chat_api, "orchestrator", None)
    monkeypatch.setattr(chat_api, "session_store", None)
    monkeypatch.setattr(chat_stream_api, "_streaming_orchestrator", None)
    monkeypatch.setattr(chat_stream_api, "_session_store", None)

    monkeypatch.setattr(
        agentic_workflow,
        "get_embedder",
        lambda: DeterministicTestEmbedder(),
    )
    monkeypatch.setattr(
        hybrid_retriever,
        "get_embedder",
        lambda: DeterministicTestEmbedder(),
    )
