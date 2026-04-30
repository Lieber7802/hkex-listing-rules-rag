from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ToolDecision(BaseModel):
    requires_tool: bool = Field(default=False, description="Whether tool invocation is needed")
    tool_name: Optional[str] = Field(default=None, description="Recommended tool name")
    tool_mode: str = Field(default="none", description="Tool routing mode: none, tool_only, tool_plus_retrieval")
    tool_inputs_hint: Dict[str, Any] = Field(default_factory=dict, description="Hint for tool inputs")
    tool_reason: Optional[str] = Field(default=None, description="Reason for tool decision")


class RouteDecision(BaseModel):
    query_type: str = Field(..., description="Query type: direct or multi_hop")
    intent: str = Field(default="general", description="Fine-grained intent classification")
    requires_decomposition: bool = Field(default=False, description="Whether task decomposition is needed")
    retrieval_strategy: str = Field(default="single_pass", description="Retrieval strategy: single_pass, multi_query, targeted_iterative")
    tool_decision: ToolDecision = Field(default_factory=ToolDecision, description="Tool decision")
    answer_format: str = Field(default="concise_with_citations", description="Expected answer format")
    route_reason: Optional[str] = Field(default=None, description="Reasoning for route decision")
    llm_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="LLM confidence score")
    validation_warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    fallback_used: bool = Field(default=False, description="Whether fallback was used")


class SubTask(BaseModel):
    id: str = Field(..., description="Unique task identifier")
    type: str = Field(..., description="Task type: retrieval, tool, reasoning_prep")
    goal: str = Field(..., description="Goal of this subtask")
    query: str = Field(..., description="Query for this subtask")
    depends_on: List[str] = Field(default_factory=list, description="IDs of tasks this depends on")
    priority: str = Field(default="medium", description="Priority: high, medium, low")
    expected_output: Optional[str] = Field(default=None, description="Expected output description")


class DecompositionPlan(BaseModel):
    subtasks: List[SubTask] = Field(default_factory=list, description="List of subtasks")
    merge_strategy: str = Field(default="sequential", description="How to merge subtask results")
    coverage_targets: List[str] = Field(default_factory=list, description="Coverage targets for evaluation")
    decomposition_reason: Optional[str] = Field(default=None, description="Reasoning for decomposition")
    llm_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="LLM confidence score")
    validation_warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    fallback_used: bool = Field(default=False, description="Whether fallback was used")


class RouteValidationResult(BaseModel):
    is_valid: bool = Field(default=True, description="Whether route decision is valid")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    conflicts: List[str] = Field(default_factory=list, description="Detected conflicts")
    should_retry: bool = Field(default=False, description="Whether to retry LLM")
    should_fallback: bool = Field(default=False, description="Whether to use heuristic fallback")


class DecompositionValidationResult(BaseModel):
    is_valid: bool = Field(default=True, description="Whether decomposition is valid")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    has_cycles: bool = Field(default=False, description="Whether dependency graph has cycles")
    incomplete_tasks: List[str] = Field(default_factory=list, description="IDs of incomplete tasks")
