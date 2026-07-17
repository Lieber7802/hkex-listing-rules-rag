import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from app.core import llm_client


def test_shared_llm_client_initialization_is_thread_safe(monkeypatch):
    created = []
    start = threading.Event()

    class _OpenAI:
        def __init__(self, **kwargs):
            start.wait(timeout=1)
            time.sleep(0.02)
            created.append(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_OpenAI))
    monkeypatch.setattr(llm_client.settings, "llm_provider", "deepseek")
    monkeypatch.setattr(llm_client.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(llm_client, "_llm_client", None)
    monkeypatch.setattr(llm_client, "_initialized", False)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(llm_client.get_llm_client) for _ in range(4)]
        start.set()
        clients = [future.result() for future in futures]

    assert len(created) == 1
    assert all(client is clients[0] for client in clients)
    assert created[0]["timeout"] == llm_client.settings.llm_timeout_seconds
