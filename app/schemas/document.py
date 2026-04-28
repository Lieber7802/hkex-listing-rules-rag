from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentMetadata(BaseModel):
    imported_at: Optional[datetime] = None
    source_url: Optional[str] = None
    page_count: Optional[int] = None


class Document(BaseModel):
    document_id: str = Field(..., description="Unique document identifier")
    source_path: str = Field(..., description="Path to source file")
    source_type: str = Field(..., description="File type: md, txt, pdf")
    title: str = Field(..., description="Document title")
    raw_text: str = Field(default="", description="Raw extracted text")
    cleaned_text: str = Field(default="", description="Cleaned text")
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class Chunk(BaseModel):
    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="Parent document ID")
    chapter: Optional[str] = Field(default=None, description="Chapter name")
    section_title: Optional[str] = Field(default=None, description="Section title")
    rule_number: Optional[str] = Field(default=None, description="Rule number")
    parent_section: Optional[str] = Field(default=None, description="Parent section path")
    chunk_order: int = Field(default=0, description="Order within the rule/section")
    char_start: int = Field(default=0, description="Start character position")
    char_end: int = Field(default=0, description="End character position")
    page_number: Optional[int] = Field(default=None, description="Page number if available")
    source_path: str = Field(..., description="Source file path")
    text: str = Field(..., description="Chunk text content")
