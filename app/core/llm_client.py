"""Shared LLM client factory — singleton pattern, lazy initialization.

All agents and services use this single factory instead of duplicating
the _get_llm_client() boilerplate in every file.

Usage:
    from app.core.llm_client import get_llm_client

    client = get_llm_client()
    if client:
        response = client.chat.completions.create(...)
"""

from __future__ import annotations

import os
from typing import Optional

from app.core.config import settings
from app.core.logger import logger

_llm_client: Optional[object] = None
_initialized: bool = False


def get_llm_client() -> Optional[object]:
    global _llm_client, _initialized
    if _initialized:
        return _llm_client
    _initialized = True

    if settings.llm_provider not in ("openai", "deepseek"):
        return None

    try:
        from openai import OpenAI

        api_key = (
            settings.llm_api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if api_key:
            _llm_client = OpenAI(api_key=api_key, base_url=settings.llm_base_url)
            logger.info(f"LLM client initialized: provider={settings.llm_provider}, model={settings.llm_model}")
        else:
            logger.warning("LLM API key not found. LLM features will use fallback paths.")
    except ImportError:
        logger.warning("openai package not installed. LLM features will use fallback paths.")

    return _llm_client
