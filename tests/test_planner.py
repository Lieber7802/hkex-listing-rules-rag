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
