"""Streaming SSE endpoint for chat v2.

POST /v2/chat/stream  — programmatic streaming
GET  /v2/chat/stream  — EventSource browser API compatibility
"""

import json
import asyncio
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents.streaming_workflow import StreamingOrchestrator
from app.services.session_store import SessionStore
from app.models.conversation import ConversationTurn
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()

_streaming_orchestrator: Optional[StreamingOrchestrator] = None
_session_store: Optional[SessionStore] = None


def get_streaming_orchestrator() -> StreamingOrchestrator:
    global _streaming_orchestrator
    if _streaming_orchestrator is None:
        _streaming_orchestrator = StreamingOrchestrator()
    return _streaming_orchestrator


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore(
            storage_path=settings.session_storage_dir,
            ttl_minutes=settings.session_ttl_minutes,
            max_turns=settings.session_max_turns,
        )
    return _session_store


async def _event_generator(query: str, use_llm_planner: bool = True, conversation_id: Optional[str] = None):
    """Async generator that yields SSE-formatted strings."""
    orch = get_streaming_orchestrator()

    if not orch.is_ready():
        yield f"event: error\ndata: {json.dumps({'message': 'Service not ready. Build index first.'})}\n\n"
        return

    try:
        # Session management
        store = get_session_store()
        session = store.get_or_create(conversation_id)
        cid = session.conversation_id

        # Get chat history
        history_turns = store.get_history(cid, max_turns=settings.session_history_window)
        chat_history = [
            {"role": t.role, "content": t.content} for t in history_turns
        ] if history_turns else None

        # Run synchronous generator in thread pool, yield events progressively via queue
        import concurrent.futures
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        finished = threading.Event()
        stream_error: Optional[Exception] = None

        def _producer():
            nonlocal stream_error
            try:
                for event in orch.stream_query(query, use_llm_planner, conversation_id=cid, chat_history=chat_history):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                stream_error = e
            finally:
                finished.set()
                loop.call_soon_threadsafe(queue.put_nowait, None)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(_producer)

        # Save user turn
        store.append_turn(cid, ConversationTurn(role="user", content=query))
        current_turn = session.turn_count

        answer_parts = []
        while True:
            event = await queue.get()
            if event is None:
                break
            event_type = event["event"]
            event_data = event["data"]

            if event_type == "done":
                event_data["conversation_id"] = cid
                event_data["turn_number"] = current_turn

            if event_type == "answer_chunk":
                answer_parts.append(event_data.get("content", ""))

            yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        if stream_error:
            logger.error(f"Streaming error: {stream_error}")
            yield f"event: error\ndata: {json.dumps({'message': str(stream_error)})}\n\n"

        executor.shutdown(wait=False)

        full_answer = "".join(answer_parts)
        if full_answer:
            store.append_turn(cid, ConversationTurn(role="assistant", content=full_answer))

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"


@router.post("/chat/stream")
async def chat_stream_post(request: dict):
    """POST endpoint for streaming chat responses."""
    query = request.get("query", "")
    use_llm_planner = request.get("use_llm_planner", True)
    conversation_id = request.get("conversation_id", None)

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    return StreamingResponse(
        _event_generator(query, use_llm_planner, conversation_id=conversation_id),
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
    conversation_id: Optional[str] = Query(default=None, description="Conversation session ID"),
):
    """GET endpoint for EventSource browser API compatibility."""
    return StreamingResponse(
        _event_generator(query, use_llm_planner, conversation_id=conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
