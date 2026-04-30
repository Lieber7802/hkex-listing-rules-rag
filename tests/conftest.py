import pytest


@pytest.fixture(autouse=True)
def no_external_services(monkeypatch):
    """Ensure tests never reach out to Ollama or external LLM APIs.

    By stripping API keys, all LLM clients remain None and agents
    fall back to heuristic paths (PlannerAgent regex, template-based
    reasoning, etc.).

    We patch both environment variables AND the settings singleton,
    because pydantic-settings reads from .env at import time.
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_api_key", None)
