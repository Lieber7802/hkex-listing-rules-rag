# HKEX RAG Tool Infrastructure Analysis

## EXECUTIVE SUMMARY

Comprehensive analysis of tool infrastructure and LangGraph V2 integration:

1. **Node Function Pattern:** Closure factory pattern - factory receives GraphNodes, returns callable node(state) -> dict
2. **Tool Executor Placement:** Recommended after decompose_router for parallel execution (Option A)
3. **AgentState Missing Fields:** tool_calls, tool_results, tool_execution_log (3 fields)
4. **Tool Catalog:** 4 tools - size_test_calculator, rule_lookup, transaction_classifier, disclosure_checklist
5. **IndexStore Gaps:** Need get_chunks_by_rule_number() and get_chunk_by_rule_and_section()
6. **State Pattern:** Accumulative (add) for lists; override for scalars

## KEY FINDINGS

### Node Pattern Analysis
All 11 nodes follow closure factory:
- Factory: def node_factory(nodes: GraphNodes): 
- Node: def node(state: AgentState) -> Dict[str, Any]:
- Pattern enables dependency injection and testability

### Tool Infrastructure
- BaseTool: abstract class with name, description, input_schema, run(), validate_inputs()
- ToolRegistry: registry with register(), get(), list_tools()
- ToolCall: auto-generated call_id (8-char UUID)
- ToolResult: paired with ToolCall via call_id

### LangGraph V2 Topology
11 nodes: llm_route_planner -> route_validator -> {heuristic_fallback | decompose_router} -> {decompose | retrieve} -> coverage_checker -> evidence_selector -> reasoning -> answer_verifier

MISSING: tool_executor_node

### AgentState (31 fields, need +3)
Current: query, query_type, route_decision, planner_output, retrieved_chunks (add), citations (add), answer, etc.
Missing: tool_calls (add), tool_results (add), tool_execution_log

### IndexStore Capabilities
- get_chunk_by_id: O(1) lookup
- search_by_vector: FAISS O(log n)
- search_by_bm25: O(n)
Missing: get_chunks_by_rule_number(), get_chunk_by_rule_and_section()

### Tool Names (4 total)
1. size_test_calculator - Market cap tests
2. rule_lookup - Rule text retrieval
3. transaction_classifier - Connected transaction classification  
4. disclosure_checklist - Disclosure requirements

## IMPLEMENTATION RECOMMENDATIONS

Phase 1: Add 3 fields to AgentState
Phase 2: Implement first tool (SizeTestCalculatorTool)
Phase 3: Implement tool_executor_node()
Phase 4: Update graph topology (add tool_executor after decompose_router)
Phase 5: Integrate tool results in reasoning
Phase 6: Full integration testing
Phase 7: Optimize IndexStore (add rule lookups)

## TOOL EXECUTOR NODE SIGNATURE

def tool_executor_node(nodes: GraphNodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        if not route_dict or not route_dict["tool_decision"].get("requires_tool"):
            return {"tool_calls": [], "tool_results": []}
        
        tool_name = route_dict["tool_decision"]["tool_name"]
        tool = nodes.tool_registry.get(tool_name)
        
        if not tool:
            # Return error ToolResult
            pass
        
        errors = tool.validate_inputs(inputs)
        if errors:
            # Return validation error ToolResult
            pass
        
        # Execute tool
        result = tool.run(inputs)
        
        # Return ToolCall + ToolResult objects
        return {"tool_calls": [...], "tool_results": [...], "tool_execution_log": "..."}
    
    return node

## RECOMMENDED GRAPH TOPOLOGY (OPTION A)

decompose_router
├─> task_decomposer -> decomposition_validator -> retriever
├─> tool_executor -> tool_integration_node -> retriever  
└─> retriever (direct)

Then: retriever -> coverage_checker -> evidence_selector -> reasoning -> answer_verifier -> END

## NEXT STEPS

1. Create ToolCall and ToolResult if not using existing schemas
2. Add 3 fields to AgentState TypedDict
3. Implement BaseTool subclasses for each tool
4. Implement tool_executor_node() closure
5. Update build_graph() to include tool_executor
6. Test with sample queries
7. Optimize IndexStore rule lookups
