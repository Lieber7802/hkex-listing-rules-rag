"""Streaming SSE endpoint for chat v2.

POST /v2/chat/stream  — programmatic streaming
GET  /v2/chat/stream  — EventSource browser API compatibility
"""

import json
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents.streaming_workflow import StreamingOrchestrator
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()

_streaming_orchestrator: Optional[StreamingOrchestrator] = None


def get_streaming_orchestrator() -> StreamingOrchestrator:
    global _streaming_orchestrator
    if _streaming_orchestrator is None:
        _streaming_orchestrator = StreamingOrchestrator()
    return _streaming_orchestrator


async def _event_generator(query: str, use_llm_planner: bool = True):
    """Async generator that yields SSE-formatted strings."""
    orch = get_streaming_orchestrator()

    if not orch.is_ready():
        yield f"event: error\ndata: {json.dumps({'message': 'Service not ready. Build index first.'})}\n\n"
        return

    try:
        # Run synchronous graph.stream() in thread pool
        loop = asyncio.get_event_loop()

        def _sync_stream():
            return list(orch.stream_query(query, use_llm_planner))

        events = await loop.run_in_executor(None, _sync_stream)

        for event in events:
            event_type = event["event"]
            event_data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {event_data}\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


@router.post("/chat/stream")
async def chat_stream_post(request: dict):
    """POST endpoint for streaming chat responses."""
    query = request.get("query", "")
    use_llm_planner = request.get("use_llm_planner", True)

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    return StreamingResponse(
        _event_generator(query, use_llm_planner),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/chat/stream")
async def chat_stream_get(
    query: str = Query(..., description="User query"),
    use_llm_planner: bool = Query(default=True),
):
    """GET endpoint for EventSource browser API compatibility."""
    return StreamingResponse(
        _event_generator(query, use_llm_planner),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
