from pydantic import BaseModel, Field
from typing import Optional


class Citation(BaseModel):
    chunk_id: str = Field(..., description="Chunk identifier")
    document_id: str = Field(..., description="Document identifier")
    rule_number: Optional[str] = Field(default=None, description="Rule number")
    section_title: Optional[str] = Field(default=None, description="Section title")
    chapter: Optional[str] = Field(default=None, description="Chapter name")
    source_path: str = Field(..., description="Source file path")
    snippet: str = Field(..., description="Text snippet from chunk")
    score: Optional[float] = Field(default=None, description="Retrieval score")
