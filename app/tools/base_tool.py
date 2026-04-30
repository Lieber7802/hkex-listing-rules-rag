from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from app.core.logger import logger


class BaseTool(ABC):
    """Base class for all tools in the HKEX RAG system.

    Subclasses must implement: name, description, input_schema, run.
    validate_inputs is provided with sensible defaults based on input_schema.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (e.g. 'size_test_calculator')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON Schema dict describing expected inputs.

        Must include 'properties' and optionally 'required'.
        Example:
            {
                "type": "object",
                "properties": {
                    "value": {"type": "number", "description": "..."}
                },
                "required": ["value"]
            }
        """
        pass

    @abstractmethod
    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool with validated inputs.

        Returns a dict of output values.
        """
        pass

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """Validate inputs against input_schema.

        Returns list of error messages (empty = valid).

        Checks:
        1. All required fields are present
        2. Field types match declared JSON Schema types
        """
        errors: List[str] = []
        schema = self.input_schema
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])

        # Check required fields
        for field in required_fields:
            if field not in inputs:
                errors.append(f"Missing required field: {field}")

        # Type validation map (JSON Schema type → Python types)
        type_map = {
            "number": (int, float),
            "integer": (int,),
            "string": (str,),
            "boolean": (bool,),
            "array": (list,),
            "object": (dict,),
        }

        # Check types for provided fields
        for field_name, field_value in inputs.items():
            if field_name in properties:
                expected_type = properties[field_name].get("type")
                if expected_type and expected_type in type_map:
                    if not isinstance(field_value, type_map[expected_type]):
                        errors.append(
                            f"Field '{field_name}' expected type '{expected_type}', "
                            f"got '{type(field_value).__name__}'"
                        )

        return errors


class ToolRegistry:
    """Registry for discovering and retrieving tools by name."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises ValueError if name already registered."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name, or None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]
