from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class QueryRequest(BaseModel):
    query: str = Field(..., description="User query text", min_length=1)


class PlannerOutput(BaseModel):
    query_type: str = Field(..., description="Query type: direct or multi_hop")
    sub_queries: List[str] = Field(default_factory=list, description="Decomposed sub-queries")
    needs_second_retrieval: bool = Field(default=False, description="Whether second retrieval is needed")
    reason: Optional[str] = Field(default=None, description="Reasoning for classification")
    intent: str = Field(default="general", description="Fine-grained intent classification")
    sub_tasks: List[str] = Field(default_factory=list, description="Structured sub-tasks")
    retrieval_strategy: str = Field(default="single_pass", description="Retrieval strategy: single_pass, multi_query, or targeted_iterative")
    requires_tool: bool = Field(default=False, description="Whether tool invocation is needed")
    evidence_requirements: Dict[str, str] = Field(default_factory=dict, description="Evidence requirements per sub-task")
    answer_format: str = Field(default="concise_with_citations", description="Expected answer format")
