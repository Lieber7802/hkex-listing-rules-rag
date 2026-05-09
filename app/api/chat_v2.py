from typing import Optional
from fastapi import APIRouter, HTTPException
from app.schemas.query import QueryRequest
from app.schemas.response import ChatResponse, HealthResponse
from app.agents.langgraph_workflow_v2 import LangGraphOrchestratorV2
from app.services.session_store import SessionStore
from app.models.conversation import ConversationTurn
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()

orchestrator: Optional[LangGraphOrchestratorV2] = None
session_store: Optional[SessionStore] = None


def get_orchestrator() -> LangGraphOrchestratorV2:
    global orchestrator
    if orchestrator is None:
        orchestrator = LangGraphOrchestratorV2()
    return orchestrator


def get_session_store() -> SessionStore:
    global session_store
    if session_store is None:
        session_store = SessionStore(
            storage_path=settings.session_storage_dir,
            ttl_minutes=settings.session_ttl_minutes,
            max_turns=settings.session_max_turns,
        )
    return session_store


@router.get("/health", response_model=HealthResponse)
async def health_check():
    orch = get_orchestrator()
    is_ready = orch.is_ready()

    return HealthResponse(
        status="ok" if is_ready else "not_ready",
        version=settings.version
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: QueryRequest):
    orch = get_orchestrator()

    if not orch.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Service not ready. Please build the index first using scripts/build_index.py"
        )

    try:
        # Session management
        store = get_session_store()
        session = store.get_or_create(request.conversation_id)
        conversation_id = session.conversation_id

        # Get chat history for LLM context
        history_turns = store.get_history(conversation_id, max_turns=settings.session_history_window)
        chat_history = [
            {"role": t.role, "content": t.content} for t in history_turns
        ] if history_turns else None

        # Process query with conversation context
        result = orch.process_query(
            request.query,
            conversation_id=conversation_id,
            chat_history=chat_history,
        )

        # Save turns to session
        store.append_turn(conversation_id, ConversationTurn(role="user", content=request.query))
        answer = result.get("answer", "No answer generated.")
        store.append_turn(
            conversation_id,
            ConversationTurn(
                role="assistant",
                content=answer,
                metadata={"citations": [str(c) for c in result.get("citations", [])]},
            ),
        )

        # Build response with conversation fields
        return ChatResponse(
            query_type=result.get("query_type", "unknown"),
            answer=answer,
            citations=result.get("citations", []),
            retrieved_chunks=result.get("retrieved_chunks", []),
            uncertainty_note=result.get("uncertainty_note"),
            route_decision=result.get("route_decision"),
            decomposition_plan=result.get("decomposition_plan"),
            route_validation=result.get("route_validation"),
            decomposition_validation=result.get("decomposition_validation"),
            coverage_assessment=result.get("coverage_assessment"),
            selected_evidence=result.get("selected_evidence"),
            verification_result=result.get("verification_result"),
            confidence_level=result.get("confidence_level"),
            retrieval_rounds=result.get("retrieval_rounds", []),
            tool_calls=result.get("tool_calls", []),
            tool_results=result.get("tool_results", []),
            conversation_id=conversation_id,
            turn_number=session.turn_count,  # Already incremented by append_turn
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )
