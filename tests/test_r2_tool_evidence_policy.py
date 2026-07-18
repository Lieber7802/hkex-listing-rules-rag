from app.agents.planner_agent import PlannerAgent


def test_regulatory_grounded_policy_routes_legal_calculation_to_tool_plus_retrieval():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")

    output = planner.plan(
        "Calculate the size test ratio and explain the disclosure obligation that follows.",
        use_llm=False,
    )

    assert output.requires_tool is True
    assert output.tool_name == "size_test_calculator"
    assert output.tool_mode == "tool_plus_retrieval"


def test_regulatory_grounded_policy_recognises_chinese_legal_consequence_terms():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "calculation_required"

    output = planner.plan(
        "请计算该交易的比率，并说明需要履行哪些披露义务。",
        use_llm=True,
    )

    assert output.requires_tool is True
    assert output.tool_mode == "tool_plus_retrieval"


def test_legacy_policy_preserves_tool_only_for_the_same_calculation_query():
    planner = PlannerAgent(tool_evidence_policy="legacy")

    output = planner.plan(
        "Calculate the size test ratio and explain the disclosure obligation that follows.",
        use_llm=False,
    )

    assert output.tool_mode == "tool_only"


def test_regulatory_grounded_policy_routes_incomplete_obligation_summary_to_retrieval_only():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "obligation_summary"

    output = planner.plan("Summarize the disclosure obligations for a listed issuer.")

    assert output.requires_tool is False
    assert output.tool_name is None
    assert output.tool_mode == "none"
    assert "routed retrieval-only" in output.reason


def test_implicit_chapter_consequence_with_complete_inputs_uses_checklist_and_retrieval():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "general"

    output = planner.plan(
        "What follows under Chapter 14 for a major transaction that is not connected "
        "and requires shareholder approval?"
    )

    assert output.intent == "obligation_summary"
    assert output.requires_tool is True
    assert output.tool_name == "disclosure_checklist"
    assert output.tool_mode == "tool_plus_retrieval"


def test_implicit_chapter_consequence_without_inputs_routes_retrieval_only():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "general"

    output = planner.plan("What follows under Chapter 14?")

    assert output.intent == "obligation_summary"
    assert output.requires_tool is False
    assert output.tool_name is None
    assert output.tool_mode == "none"


def test_chinese_implicit_chapter_consequence_with_complete_inputs_uses_checklist_and_retrieval():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "general"

    output = planner.plan(
        "\u6839\u636e\u7b2c14\u7ae0\uff0c\u4e3b\u8981\u4ea4\u6613\u4e0d\u662f\u5173\u8054\u4ea4\u6613"
        "\u4e14\u9700\u8981\u80a1\u4e1c\u6279\u51c6\uff0c\u540e\u7eed\u9700\u8981\u5c65\u884c\u4ec0\u4e48\u4e49\u52a1\uff1f"
    )

    assert output.intent == "obligation_summary"
    assert output.requires_tool is True
    assert output.tool_name == "disclosure_checklist"
    assert output.tool_mode == "tool_plus_retrieval"


def test_comparison_with_ratio_language_does_not_execute_an_unnamed_tool():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")

    output = planner.plan(
        "Compare the asset ratio disclosure requirements for two transaction types.",
        use_llm=False,
    )

    assert output.intent == "comparison"
    assert output.requires_tool is False
    assert output.tool_name is None


def test_tool_input_extraction_combines_partial_llm_output_with_heuristic_values(monkeypatch):
    from app.agents import tool_input_extraction_node as extraction

    monkeypatch.setattr(extraction, "_llm_extract", lambda query, tool_name: {
        "transaction_consideration": 250,
    })
    monkeypatch.setattr(extraction, "_heuristic_extract", lambda query, tool_name: {
        "transaction_type": "acquisition",
        "issuer_market_cap": 1000,
    })

    inputs = extraction.extract_tool_inputs("calculate a transaction", "size_test_calculator")

    assert inputs == {
        "transaction_consideration": 250,
        "transaction_type": "acquisition",
        "issuer_market_cap": 1000,
    }


def test_complete_heuristic_tool_inputs_skip_the_llm_extractor(monkeypatch):
    from app.agents import tool_input_extraction_node as extraction

    monkeypatch.setattr(extraction, "_heuristic_extract", lambda query, tool_name: {
        "transaction_consideration": 250,
        "transaction_type": "acquisition",
    })
    monkeypatch.setattr(extraction, "_llm_extract", lambda query, tool_name: (_ for _ in ()).throw(
        AssertionError("LLM extractor should not run when required inputs are present")
    ))

    inputs = extraction.extract_tool_inputs("calculate a transaction", "size_test_calculator")

    assert inputs["transaction_consideration"] == 250
