from app.agents.tool_input_extraction_node import extract_tool_inputs


def test_disclosure_checklist_extraction_respects_explicit_negative_connection_status():
    inputs = extract_tool_inputs(
        "For a major transaction that is not connected and requires shareholder approval, "
        "what disclosure steps apply?",
        "disclosure_checklist",
    )

    assert inputs == {
        "classification": "major_transaction",
        "is_connected": False,
        "shareholder_vote_required": True,
    }


def test_disclosure_checklist_extraction_does_not_invent_missing_required_facts():
    inputs = extract_tool_inputs(
        "What disclosure steps apply to a major transaction?",
        "disclosure_checklist",
    )

    assert inputs.get("classification") == "major_transaction"
    assert "is_connected" not in inputs
    assert "shareholder_vote_required" not in inputs
