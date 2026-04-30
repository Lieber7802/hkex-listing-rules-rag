# Phase 2 Stage 2: HKEX Tool Integration — Implementation Plan

## Context

Phase 2 Stage 1 (agentic graph reinforcement) and the Planner refactor are complete. The tool infrastructure (BaseTool, ToolRegistry, ToolCall/ToolResult schemas) is in place. The V2 LangGraph workflow has `ToolDecision` flowing through `route_decision` but no tool is actually executed — `tool_executor_node` doesn't exist yet. This plan implements all 4 HKEX-specific tools and wires them into the V2 graph.

---

## Sprint Overview

```
Sprint 1: State + IndexStore extensions (foundation)          ✅
Sprint 2: SizeTestCalculatorTool (core financial tool)        ✅
Sprint 3: TransactionClassifierTool                           ✅
Sprint 4: DisclosureChecklistTool                             ✅
Sprint 5: RuleLookupTool (depends on Sprint 1 IndexStore)     ✅
Sprint 6: ToolExecutor node + graph wiring                    ✅
Sprint 7: Planner tool routing enhancement                    ✅
Sprint 8: End-to-end integration tests + API + docs           ✅
```

---

## Sprint 1: Foundation — State & IndexStore ✅

### 1a. Add tool fields to AgentState

**Edit:** `app/agents/graph_state.py` — add 2 accumulative fields:
```python
tool_calls: Annotated[List[Dict[str, Any]], add]
tool_results: Annotated[List[Dict[str, Any]], add]
```
- [x] Added `tool_calls` and `tool_results` to AgentState

### 1b. Add `get_chunks_by_rule_number` to IndexStore

**Edit:** `app/retrieval/index_store.py` — add to `IndexStore`:
```python
def get_chunks_by_rule_number(self, rule_number: str) -> List[Chunk]:
    return [c for c in self.chunks if c.rule_number == rule_number]
```
- [x] Added method with chunk_order sorting

**New file:** `tests/test_index_store_lookup.py` (~3 tests)
- [x] Matching rule_number → chunks returned
- [x] Non-matching → empty list
- [x] None rule_number chunks excluded
- [x] Empty chunks list → empty
- [x] Results preserve chunk_order

### 1c. Update initial state

**Edit:** `app/agents/langgraph_workflow_v2.py` — add `"tool_calls": [], "tool_results": []` to initial state dict.
- [x] Updated V2 initial state
- [x] Updated V1 initial state for AgentState compatibility

---

## Sprint 2: SizeTestCalculatorTool ✅

**New file:** `app/tools/size_test_calculator.py`

### Input (all in HK$ millions)
```
issuer_market_cap, issuer_total_assets, issuer_net_assets,
issuer_annual_profit, issuer_shares_outstanding,
transaction_consideration, acquired_assets, acquired_profit,
acquired_net_assets, consideration_shares (default 0),
transaction_type ("acquisition"|"disposal")
```

### Output
```json
{
  "ratios": {
    "consideration_ratio": 25.0,
    "assets_ratio": 30.0,
    "profits_ratio": 60.0,
    "shares_ratio": 20.0,
    "net_assets_ratio": 30.0
  },
  "highest_ratio": 60.0,
  "highest_ratio_name": "profits_ratio",
  "suggested_classification": "major_transaction",
  "warnings": []
}
```

### Logic
- [x] Each ratio = (acquired / issuer) × 100, rounded to 1 decimal
- [x] shares_ratio = 0 if consideration_shares == 0
- [x] Classification by highest ratio + transaction_type
- [x] Edge cases: negative profit → abs value + warning; zero denominator → validation error; ratio > 500% → warning

**New file:** `tests/test_size_test_calculator.py` (21 tests)
- [x] Known ratio computation
- [x] Each threshold boundary (4.9/5.0, 24.9/25.0, 49.9/50.0, 99.9/100.0)
- [x] Disposal thresholds (74.9/75.0)
- [x] Cash-only (shares_ratio=0)
- [x] Negative profit
- [x] Zero denominator rejection
- [x] Input validation

---

## Sprint 3: TransactionClassifierTool ✅

**New file:** `app/tools/transaction_classifier.py`

- [x] Map highest_ratio + transaction_type → classification (same thresholds as Sprint 2)
- [x] If is_connected: override disclosure_level→"very_high", shareholder_vote→true, ifa→true, add Chapter 14A rules
- [x] Generate display_name, chapter, primary_rule, applicable_rules

**New file:** `tests/test_transaction_classifier.py` (15 tests)
- [x] Each classification tier
- [x] Acquisition vs disposal threshold difference
- [x] Connected transaction override (vote, IFA, disclosure level, 14A rules)

---

## Sprint 4: DisclosureChecklistTool ✅

**New file:** `app/tools/disclosure_checklist.py`

- [x] Structured checklist with sections: announcement, circular, shareholder_meeting, post_completion
- [x] Content by classification (de minimis → very substantial)
- [x] Connected overlay: + IFA opinion + independent shareholder approval + Chapter 14A items

**New file:** `tests/test_disclosure_checklist.py` (14 tests)
- [x] De minimis minimal disclosure
- [x] Share transaction announcement
- [x] Major/very substantial full sections
- [x] Connected overlay adds IFA + 14A rules
- [x] Item structure validation

---

## Sprint 5: RuleLookupTool ✅

**New file:** `app/tools/rule_lookup.py`

- [x] Constructor takes `IndexStore` (dependency injection)
- [x] Uses `index_store.get_chunks_by_rule_number(rule_number)`
- [x] Normalizes input: strip "Rule " prefix, trim whitespace
- [x] Returns chunks sorted by chunk_order

**New file:** `tests/test_rule_lookup.py` (11 tests)
- [x] Exact match, chunk data, sorted order
- [x] Chapter letter rules (14A.35)
- [x] Input normalization (strip prefix, whitespace)
- [x] Not found → empty

---

## Sprint 6: ToolExecutor Node + Graph Wiring ✅

### 6a. tool_executor_node

**Edit:** `app/agents/langgraph_workflow_v2.py`

- [x] Add `ToolRegistry` and register all 4 tools in `GraphNodes.__init__`
- [x] Create `tool_executor_node()` — reads `route_decision.tool_decision`, looks up tool, validates, runs, stores ToolCall + ToolResult

### 6b. tool_mode_router

- [x] `tool_only` → "select" (skip retrieval, go to evidence_selector)
- [x] `tool_plus_retrieval` → "retrieve" (continue to retriever)

### 6c. Replace should_decompose → should_route (3-way)

- [x] `requires_decomposition` → "decompose"
- [x] `requires_tool` → "execute_tool"
- [x] else → "retrieve"

### 6d. New graph topology

- [x] Rewired graph with tool_executor node and 3-way routing
```
decompose_router → [should_route]
  decompose    → task_decomposer → decomposition_validator → retriever
  execute_tool → tool_executor → [tool_mode_router]
      select   → evidence_selector (skip retrieval for tool_only)
      retrieve → retriever (tool_plus_retrieval)
  retrieve     → retriever (no tool)
```

### 6e. Update reasoning_node

- [x] When `retrieved_chunks` is empty but `tool_results` has successful output, format tool output as answer

**New file:** `tests/test_tool_executor.py` (8 tests)
- [x] Tool found → success result
- [x] Tool not found → error result
- [x] Validation fails → error with message
- [x] tool_mode_router routing (tool_only → select, tool_plus_retrieval → retrieve)
- [x] should_route 3-way routing (decompose, execute_tool, retrieve)

---

## Sprint 7: Planner Tool Routing Enhancement ✅

### 7a. Add tool_name/tool_mode selection to PlannerAgent

**Edit:** `app/agents/planner_agent.py`
- [x] `_select_tool_name(intent, query)` → maps intent to tool_name
- [x] `_select_tool_mode(intent)` → maps intent to tool_mode
- [x] Updated `_requires_tool` to include rule_lookup and eligibility_check

### 7b. Add fields to PlannerOutput

**Edit:** `app/schemas/query.py`
- [x] Add: `tool_name: Optional[str]`, `tool_mode: str = "none"`

### 7c. Fix hardcoded fallback tool_name

**Edit:** `app/agents/langgraph_workflow_v2.py`
- [x] Replace `tool_name="size_test_calculator"` with `tool_name=planner_output.tool_name` in both `llm_route_planner_node` and `heuristic_fallback_node`

**New file:** `tests/test_planner_tool_routing.py` (14 tests)
- [x] PlannerOutput field existence and defaults
- [x] _select_tool_name mapping (calculation → size_test, rule_lookup → rule_lookup, eligibility → classifier, general → None)
- [x] _select_tool_mode mapping
- [x] Integration: plan() sets correct tool_name + tool_mode for different queries

---

## Sprint 8: Integration + API + Docs ✅

### 8a. End-to-end tests

**New file:** `tests/test_tool_integration.py` (5 tests)
- [x] "Calculate size test" → tool_executor fires, tool_results populated
- [x] Regular query → no tool, tool_calls empty
- [x] Rule lookup query → rule_lookup tool fires
- [x] process_query returns tool_calls and tool_results fields
- [x] tool_only mode provides answer without retrieval

### 8b. Update API response

- [x] **Edit:** `app/schemas/response.py` — add `tool_calls`, `tool_results` fields
- [x] **Edit:** `app/api/chat_v2.py` — pass tool fields from result to response
- [x] **Edit:** `app/agents/langgraph_workflow_v2.py` — add tool fields to process_query return

### 8c. Documentation

- [x] **Edit:** `CLAUDE.md` — updated V2 workflow topology, tool modules, state accumulation docs

---

## File Change Summary

| File | Action | Sprint | Status |
|------|--------|--------|--------|
| `app/agents/graph_state.py` | Edit (+2 fields) | 1 | ✅ |
| `app/retrieval/index_store.py` | Edit (+1 method) | 1 | ✅ |
| `app/agents/langgraph_workflow_v2.py` | Edit (initial state) | 1 | ✅ |
| `tests/test_index_store_lookup.py` | **New** | 1 | ✅ |
| `app/tools/size_test_calculator.py` | **New** | 2 | ✅ |
| `tests/test_size_test_calculator.py` | **New** | 2 | ✅ |
| `app/tools/transaction_classifier.py` | **New** | 3 | ✅ |
| `tests/test_transaction_classifier.py` | **New** | 3 | ✅ |
| `app/tools/disclosure_checklist.py` | **New** | 4 | ✅ |
| `tests/test_disclosure_checklist.py` | **New** | 4 | ✅ |
| `app/tools/rule_lookup.py` | **New** | 5 | ✅ |
| `tests/test_rule_lookup.py` | **New** | 5 | ✅ |
| `app/agents/langgraph_workflow_v2.py` | Edit (executor, graph) | 6 | ✅ |
| `tests/test_tool_executor.py` | **New** | 6 | ✅ |
| `app/agents/planner_agent.py` | Edit (tool routing) | 7 | ✅ |
| `app/schemas/query.py` | Edit (+2 fields) | 7 | ✅ |
| `tests/test_planner_tool_routing.py` | **New** | 7 | ✅ |
| `tests/test_tool_integration.py` | **New** | 8 | ✅ |
| `app/schemas/response.py` | Edit (+2 fields) | 8 | ✅ |
| `app/api/chat_v2.py` | Edit | 8 | ✅ |
| `CLAUDE.md` | Edit | 8 | ✅ |

**Total: 10 new files, 11 edited files, 93 new tests — ALL COMPLETE**

---

## Verification ✅

```bash
pytest tests/ -v    # 195 passed, 0 failed
```
