from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from app.schemas.citation import Citation
from app.schemas.query import PlannerOutput


class ChatResponse(BaseModel):
    query_type: str = Field(..., description="Query type: direct or multi_hop")
    answer: str = Field(..., description="Generated answer")
    citations: List[Citation] = Field(default_factory=list, description="Supporting citations")
    retrieved_chunks: List[Any] = Field(default_factory=list, description="Retrieved chunk data")
    uncertainty_note: Optional[str] = Field(default=None, description="Note if evidence is partial")
    planner_output: Optional[PlannerOutput] = Field(default=None, description="Planner decision details")
    coverage_assessment: Optional[Dict[str, Any]] = Field(default=None, description="Evidence coverage assessment")
    selected_evidence: Optional[Dict[str, Any]] = Field(default=None, description="Selected evidence details")
    verification_result: Optional[Dict[str, Any]] = Field(default=None, description="Answer verification result")
    confidence_level: Optional[str] = Field(default=None, description="Confidence level: high, medium, low")
    retrieval_rounds: List[Dict[str, Any]] = Field(default_factory=list, description="Retrieval round history")
    route_decision: Optional[Dict[str, Any]] = Field(default=None, description="LLM route decision")
    decomposition_plan: Optional[Dict[str, Any]] = Field(default=None, description="Task decomposition plan")
    route_validation: Optional[Dict[str, Any]] = Field(default=None, description="Route validation result")
    decomposition_validation: Optional[Dict[str, Any]] = Field(default=None, description="Decomposition validation result")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tool calls made during processing")
    tool_results: List[Dict[str, Any]] = Field(default_factory=list, description="Tool execution results")


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Service status")
    version: str = Field(..., description="Service version")
