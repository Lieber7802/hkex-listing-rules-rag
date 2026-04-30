from typing import Optional
from fastapi import APIRouter, HTTPException
from app.schemas.query import QueryRequest
from app.schemas.response import ChatResponse, HealthResponse
from app.agents.langgraph_workflow import LangGraphOrchestrator
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()

orchestrator: Optional[LangGraphOrchestrator] = None


def get_orchestrator() -> LangGraphOrchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = LangGraphOrchestrator()
    return orchestrator


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
        result = orch.process_query(request.query)
        
        return ChatResponse(
            query_type=result.get("query_type", "unknown"),
            answer=result.get("answer", "No answer generated."),
            citations=result.get("citations", []),
            retrieved_chunks=result.get("retrieved_chunks", []),
            uncertainty_note=result.get("uncertainty_note"),
            planner_output=result.get("planner_output"),
            coverage_assessment=result.get("coverage_assessment"),
            selected_evidence=result.get("selected_evidence"),
            verification_result=result.get("verification_result"),
            confidence_level=result.get("confidence_level"),
            retrieval_rounds=result.get("retrieval_rounds", [])
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )
