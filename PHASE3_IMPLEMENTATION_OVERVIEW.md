# Phase 3: LLM-Based Tool Input Extraction

## Executive Summary

**Problem:** Tool infrastructure is complete but non-functional because `tool_inputs_hint` is always empty `{}`, causing all tool executions to fail validation.

**Solution:** Implement a 3-layer extraction strategy (LLM → Heuristic → Recovery) to populate tool inputs from natural language queries.

**Deliverables:** 
- 10 new files (utilities, nodes, tests)
- 8 file edits (prompts, schema, integration)  
- 115+ tests across all sprints
- Complete documentation

**Effort:** 16-20 hours across 6 focused sprints

---

## Current State: Why Tools Don't Work

### The Root Cause

File: `app/agents/llm_route_planner.py`

**Line 112** (LLM path):
```
tool_inputs_hint={}  # ALWAYS EMPTY
```

**Line 139** (Heuristic fallback):
```
tool_inputs_hint={}  # ALWAYS EMPTY
```

### Execution Flow Breakdown

1. User query: "Calculate size test with market cap 1000m"
2. LLMRoutePlanner creates: `tool_decision.tool_inputs_hint = {}`
3. tool_executor_node receives empty inputs
4. Validation fails: "Missing required field: issuer_total_assets"
5. Tool never executes
6. User gets error

### What Should Happen

1. User query: "Calculate size test with market cap 1000m"
2. **Layer 1 (LLM):** Extract `issuer_market_cap: 1000000000` from query
3. **Layer 2 (Heuristic):** Extract percentages, transaction type, etc.
4. **Layer 3 (Recovery):** If validation fails, retry extraction
5. Tool executes with partial or full inputs
6. User gets result (or graceful error about missing required fields)

---

## Sprint Breakdown (6 Sprints, 16-20 Hours)

**Sprint 1: QueryParser Module (2 hours)**
- Create reusable utilities for extracting typed data
- 7 static methods (no state)
- 59 tests
- Files: app/tools/query_parser.py, tests/test_query_parser.py

**Sprint 2: LLM Prompt Enhancement (1.5 hours)**
- Make LLM extract and return tool_inputs_hint
- 12 tests
- Files: Edit app/agents/llm_route_planner.py

**Sprint 3: Size Test Extractor (2.5 hours)**
- Extract 10 financial fields from queries
- 16 tests
- Files: app/tools/size_test_input_extractor.py

**Sprint 4: Tool Input Extraction Node (2 hours)**
- Integrate extraction into V2 graph
- 10 tests
- Files: app/agents/tool_input_extraction_node.py

**Sprint 5: Fallback Integration (1.5 hours)**
- Attempt extraction on validation failure
- Tests covered by existing
- Files: Edit app/agents/langgraph_workflow_v2.py

**Sprint 6: End-to-End Testing + Documentation (2 hours)**
- Prove all tools work end-to-end
- 8 tests
- Files: tests/test_tool_input_extraction_e2e.py, docs/

---

## Success Criteria

**Functional:**
- All 4 tools execute end-to-end
- No "Missing required field" errors on extractable queries
- SizeTest gets 50%+ field extraction on typical queries
- API response includes extraction_log for debugging
- Zero tool_inputs_hint={} in successful executions

**Quality:**
- All 115+ tests pass
- >90% code coverage
- No new technical debt

**Documentation:**
- Comprehensive guide in docs/tool-input-extraction.md
- CLAUDE.md updated
- Code comments for non-obvious logic

---

## File Changes

**New Files (10):**
1. app/tools/query_parser.py
2. app/tools/size_test_input_extractor.py
3. app/agents/tool_input_extraction_node.py
4. tests/test_query_parser.py
5. tests/test_llm_route_planner_input_extraction.py
6. tests/test_size_test_input_extractor.py
7. tests/test_tool_input_extraction_node.py
8. tests/test_tool_input_extraction_e2e.py
9. docs/tool-input-extraction.md
10. Plan files in docs/superpowers/plans/

**Edited Files (8):**
1. app/agents/llm_route_planner.py (enhance prompts, parse inputs)
2. app/agents/langgraph_workflow_v2.py (integrate node, fallback)
3. app/agents/graph_state.py (add extraction_log field)
4. app/schemas/response.py (add extraction fields)
5. app/api/chat_v2.py (pass extraction to response)
6. CLAUDE.md (add extraction section)

---

## Next Steps

1. Read PHASE3_SUMMARY.txt for high-level overview
2. Read docs/superpowers/plans/SPRINT1_SPECIFICATION.txt for detailed first sprint
3. Begin implementation with TDD: write tests first
4. Each sprint has clear acceptance criteria

---

See supporting documents:
- PHASE3_SUMMARY.txt (executive summary)
- docs/superpowers/plans/PHASE3_SUMMARY.txt (duplicate)
- docs/superpowers/plans/SPRINT1_SPECIFICATION.txt (detailed Sprint 1)

