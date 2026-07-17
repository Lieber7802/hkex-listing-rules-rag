import pytest
from app.agents.planner_agent import PlannerAgent, plan_query
from app.schemas.query import PlannerOutput


class TestPlannerAgent:
    
    def test_classify_direct_simple_lookup(self):
        planner = PlannerAgent()
        output = planner.plan("What is Rule 14A.35?")
        assert output.query_type == "direct"
        assert len(output.sub_queries) == 1
        assert output.needs_second_retrieval == False
    
    def test_classify_direct_definition(self):
        planner = PlannerAgent()
        output = planner.plan("Define connected transaction")
        assert output.query_type == "direct"
    
    def test_classify_direct_requirements(self):
        planner = PlannerAgent()
        output = planner.plan("What are the disclosure requirements for notifiable transactions?")
        assert output.query_type == "direct"
    
    def test_classify_multi_hop_with_and(self):
        planner = PlannerAgent()
        output = planner.plan("What are the disclosure requirements for connected transactions and how do they differ from notifiable transactions?")
        assert output.query_type == "multi_hop"
        assert len(output.sub_queries) > 1
    
    def test_classify_multi_hop_comparison(self):
        planner = PlannerAgent()
        output = planner.plan("Compare the size test thresholds for connected transactions versus notifiable transactions")
        assert output.query_type == "multi_hop"
        assert output.needs_second_retrieval == True
    
    def test_sub_queries_generated_for_multi_hop(self):
        planner = PlannerAgent()
        output = planner.plan("What are the requirements for Rule 14A.35 and Rule 14A.36?")
        assert output.query_type == "multi_hop"
        assert len(output.sub_queries) >= 2
    
    def test_reason_is_provided(self):
        planner = PlannerAgent()
        output = planner.plan("What is the disclosure obligation?")
        assert output.reason is not None
        assert len(output.reason) > 0
    
    def test_needs_second_retrieval_for_complex_queries(self):
        planner = PlannerAgent()
        output = planner.plan("What is the relationship between connected transactions and major transactions and how do their disclosure requirements differ?")
        assert output.needs_second_retrieval == True
    
    def test_plan_query_function(self):
        output = plan_query("What is Rule 14A.35?")
        assert isinstance(output, PlannerOutput)
        assert output.query_type in ["direct", "multi_hop"]
    
    def test_deterministic_output(self):
        planner = PlannerAgent()
        query = "What are the disclosure requirements for connected transactions?"
        output1 = planner.plan(query)
        output2 = planner.plan(query)
        assert output1.query_type == output2.query_type
        assert output1.sub_queries == output2.sub_queries
        assert output1.needs_second_retrieval == output2.needs_second_retrieval

    def test_registration_rule_query_is_not_mistaken_for_a_ratio_calculation(self):
        planner = PlannerAgent()

        output = planner.plan(
            "What does GEM Rule 6A.30 require if a sponsor's registration is revoked?",
            use_llm=False,
        )

        assert output.intent == "rule_lookup"
        assert output.requires_tool is True
        assert output.tool_name == "rule_lookup"

    def test_procedure_request_with_a_rule_reference_keeps_procedure_intent(self):
        planner = PlannerAgent()

        output = planner.plan(
            "What procedure is required by GEM Rule 30.30 before a listing document is issued?",
            use_llm=False,
        )

        assert output.intent == "procedure_flow"
        assert output.requires_tool is False

    def test_llm_calculation_misclassification_is_corrected_for_registration_rule_query(self):
        planner = PlannerAgent()
        planner._classify_intent_with_llm = lambda query: "calculation_required"

        output = planner.plan(
            "What does GEM Rule 6A.30 require if a sponsor's registration is revoked?",
            use_llm=True,
        )

        assert output.intent == "rule_lookup"
        assert "corrected calculation_required to rule_lookup" in output.reason

    def test_calculation_input_clauses_stay_in_one_tool_workflow(self):
        planner = PlannerAgent()

        output = planner.plan(
            "Calculate the size test using total assets and consideration and explain disclosure.",
            use_llm=False,
        )

        assert output.intent == "calculation_required"
        assert output.query_type == "direct"
        assert output.needs_second_retrieval is False

    def test_chinese_obligation_summary_with_rule_reference_avoids_rule_lookup_tool(self):
        planner = PlannerAgent()

        output = planner.plan(
            "\u8bf7\u6839\u636e Main Board Rule 21.14 \u7684\u8bc1\u636e\u6bb5\u843d"
            "\u6982\u62ec\u53d1\u884c\u4eba\u9700\u8981\u6ce8\u610f\u7684"
            "\u62ab\u9732\u6216\u5408\u89c4\u4e49\u52a1\u3002",
            use_llm=False,
        )

        assert output.intent == "obligation_summary"
        assert output.requires_tool is False
