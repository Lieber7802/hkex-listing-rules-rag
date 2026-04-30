from typing import TypedDict, List, Optional, Annotated, Dict, Any
from operator import add

from app.schemas.document import Chunk
from app.schemas.query import PlannerOutput
from app.schemas.citation import Citation


class AgentState(TypedDict):
    query: str
    planner_output: Optional[PlannerOutput]
    retrieved_chunks: Annotated[List[dict], add]
    citations: Annotated[List[Citation], add]
    answer: Optional[str]
    uncertainty_note: Optional[str]
    query_type: Optional[str]
    error: Optional[str]
    needs_second_retrieval: bool
    iteration_count: int
    coverage_assessment: Optional[Dict[str, Any]]
    selected_evidence: Optional[Dict[str, Any]]
    verification_result: Optional[Dict[str, Any]]
    confidence_level: Optional[str]
    retrieval_rounds: Annotated[List[Dict[str, Any]], add]
    route_decision: Optional[Dict[str, Any]]
    decomposition_plan: Optional[Dict[str, Any]]
    route_validation: Optional[Dict[str, Any]]
    decomposition_validation: Optional[Dict[str, Any]]
    use_llm_planner: bool
    route_retry_count: int
    tool_calls: Annotated[List[Dict[str, Any]], add]
    tool_results: Annotated[List[Dict[str, Any]], add]
