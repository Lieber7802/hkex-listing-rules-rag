from typing import Optional
from fastapi import APIRouter, HTTPException
from app.schemas.query import QueryRequest
from app.schemas.response import ChatResponse, HealthResponse
from app.agents.langgraph_workflow_v2 import LangGraphOrchestratorV2
from app.core.config import settings
from app.core.logger import logger

router = APIRouter()

orchestrator: Optional[LangGraphOrchestratorV2] = None


def get_orchestrator() -> LangGraphOrchestratorV2:
    global orchestrator
    if orchestrator is None:
        orchestrator = LangGraphOrchestratorV2()
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
            route_decision=result.get("route_decision"),
            decomposition_plan=result.get("decomposition_plan"),
            route_validation=result.get("route_validation"),
            decomposition_validation=result.get("decomposition_validation"),
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
