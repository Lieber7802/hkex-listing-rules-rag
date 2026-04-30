from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import uuid


class ToolCall(BaseModel):
    """Represents a request to invoke a tool."""

    call_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique call identifier",
    )
    tool_name: str = Field(..., description="Name of the tool to invoke")
    inputs: Dict[str, Any] = Field(
        default_factory=dict, description="Input parameters for the tool"
    )


class ToolResult(BaseModel):
    """Represents the result of a tool invocation."""

    call_id: str = Field(..., description="Matching call identifier")
    tool_name: str = Field(..., description="Name of the tool that was invoked")
    success: bool = Field(..., description="Whether the invocation succeeded")
    output: Optional[Dict[str, Any]] = Field(
        default=None, description="Tool output on success"
    )
    error: Optional[str] = Field(
        default=None, description="Error message on failure"
    )
