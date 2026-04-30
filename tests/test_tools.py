import pytest
from typing import Dict, Any
from app.tools.base_tool import BaseTool, ToolRegistry
from app.schemas.tool import ToolCall, ToolResult


class MockCalculatorTool(BaseTool):
    """Concrete test tool implementing all abstract methods."""

    @property
    def name(self) -> str:
        return "size_test_calculator"

    @property
    def description(self) -> str:
        return "Calculates HKEX size test ratios for notifiable transactions"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "assets_value": {"type": "number", "description": "Total assets value"},
                "transaction_value": {"type": "number", "description": "Transaction value"},
            },
            "required": ["assets_value", "transaction_value"],
        }

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ratio = inputs["transaction_value"] / inputs["assets_value"]
        return {"ratio": ratio, "percentage": f"{ratio * 100:.2f}%"}


class TestBaseTool:

    def test_tool_has_name(self):
        tool = MockCalculatorTool()
        assert tool.name == "size_test_calculator"

    def test_tool_has_description(self):
        tool = MockCalculatorTool()
        assert "size test" in tool.description.lower()

    def test_tool_has_input_schema(self):
        tool = MockCalculatorTool()
        schema = tool.input_schema
        assert "properties" in schema
        assert "assets_value" in schema["properties"]

    def test_validate_inputs_passes_valid(self):
        tool = MockCalculatorTool()
        errors = tool.validate_inputs({"assets_value": 1000, "transaction_value": 100})
        assert errors == []

    def test_validate_inputs_catches_missing_required(self):
        tool = MockCalculatorTool()
        errors = tool.validate_inputs({"assets_value": 1000})
        assert len(errors) > 0
        assert any("transaction_value" in e for e in errors)

    def test_validate_inputs_catches_wrong_type(self):
        tool = MockCalculatorTool()
        errors = tool.validate_inputs({"assets_value": "not_a_number", "transaction_value": 100})
        assert len(errors) > 0

    def test_run_returns_result(self):
        tool = MockCalculatorTool()
        result = tool.run({"assets_value": 1000, "transaction_value": 250})
        assert result["ratio"] == 0.25


class TestToolRegistry:

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = MockCalculatorTool()
        registry.register(tool)
        assert registry.get("size_test_calculator") is tool

    def test_get_returns_none_for_unknown(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(MockCalculatorTool())
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "size_test_calculator"
        assert "description" in tools[0]

    def test_duplicate_registration_raises(self):
        registry = ToolRegistry()
        registry.register(MockCalculatorTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(MockCalculatorTool())


class TestToolSchemas:

    def test_tool_call_creation(self):
        call = ToolCall(
            tool_name="size_test_calculator",
            inputs={"assets_value": 1000, "transaction_value": 100},
        )
        assert call.tool_name == "size_test_calculator"
        assert call.call_id is not None

    def test_tool_result_success(self):
        result = ToolResult(
            call_id="abc-123",
            tool_name="size_test_calculator",
            success=True,
            output={"ratio": 0.1},
        )
        assert result.success is True
        assert result.error is None

    def test_tool_result_failure(self):
        result = ToolResult(
            call_id="abc-123",
            tool_name="size_test_calculator",
            success=False,
            error="Division by zero",
        )
        assert result.success is False
        assert result.output is None
