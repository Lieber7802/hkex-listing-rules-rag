"""Tool chain definitions for HKEX compliance workflows.

Defines which tools can feed into which, and how to map outputs→inputs.
Chain: size_test_calculator → transaction_classifier → disclosure_checklist
"""

from typing import Dict, Any, List, Optional, Tuple

from app.core.logger import logger


# ── Chain definitions ────────────────────────────────────────────
# Format: source_tool → list of chain steps

TOOL_CHAINS: Dict[str, List[Dict[str, Any]]] = {
    "size_test_calculator": [
        {
            "target": "transaction_classifier",
            "output_mapping": {
                "highest_ratio": "highest_ratio",
            },
            "static_defaults": {
                "is_connected": False,
                "transaction_type": "acquisition",
            },
            "required_output_fields": ["highest_ratio"],
            "condition": lambda output: output.get("highest_ratio") is not None,
        },
    ],
    "transaction_classifier": [
        {
            "target": "disclosure_checklist",
            "output_mapping": {
                "classification": "classification",
                "shareholder_vote_required": "shareholder_vote_required",
            },
            "static_defaults": {
                "is_connected": False,
            },
            "required_output_fields": ["classification", "shareholder_vote_required"],
            "condition": lambda output: output.get("classification") is not None,
        },
    ],
}


def resolve_chain_inputs(
    source_tool: str,
    source_output: Dict[str, Any],
    target_tool: str,
    user_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve inputs for a downstream tool from the source tool's output.

    Returns None if chain is not applicable or conditions not met.
    """
    chain_defs = TOOL_CHAINS.get(source_tool, [])

    for chain_def in chain_defs:
        if chain_def["target"] != target_tool:
            continue

        # Check condition
        condition = chain_def.get("condition")
        if condition and not condition(source_output):
            return None

        # Check required output fields exist
        for field in chain_def["required_output_fields"]:
            if field not in source_output:
                logger.warning(f"Chain {source_tool}→{target_tool}: missing '{field}' in output")
                return None

        # Build inputs from output mapping
        inputs: Dict[str, Any] = {}
        for output_field, input_field in chain_def["output_mapping"].items():
            if input_field is not None and output_field in source_output:
                inputs[input_field] = source_output[output_field]

        # Apply static defaults
        for key, value in chain_def["static_defaults"].items():
            if key not in inputs:
                inputs[key] = value

        # Override with user context
        for key, value in user_context.items():
            if key in inputs or key in chain_def.get("static_defaults", {}):
                inputs[key] = value

        return inputs

    return None


def should_chain(tool_name: str, tool_output: Dict[str, Any]) -> bool:
    """Quick check: does this tool have any applicable downstream chain targets?"""
    if tool_name not in TOOL_CHAINS:
        return False

    for chain_def in TOOL_CHAINS[tool_name]:
        condition = chain_def.get("condition")
        if condition is None or condition(tool_output):
            return True

    return False


def get_next_chain_target(
    source_tool: str,
    source_output: Dict[str, Any],
    user_context: Dict[str, Any],
    visited: set,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Get the next chain target and its resolved inputs.

    Returns (target_name, resolved_inputs) or None.
    """
    chain_defs = TOOL_CHAINS.get(source_tool, [])

    for chain_def in chain_defs:
        target = chain_def["target"]
        if target in visited:
            continue

        inputs = resolve_chain_inputs(source_tool, source_output, target, user_context)
        if inputs is not None:
            return (target, inputs)

    return None
