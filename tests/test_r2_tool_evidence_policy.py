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


def test_regulatory_grounded_policy_marks_obligation_summaries_for_retrieval():
    planner = PlannerAgent(tool_evidence_policy="regulatory_grounded")
    planner._classify_intent_with_llm = lambda query: "obligation_summary"

    output = planner.plan("Summarize the disclosure obligations for a listed issuer.")

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
