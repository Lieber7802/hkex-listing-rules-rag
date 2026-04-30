# Implementation Plan: Resolve Outstanding Items

## Context

The HKEX Listing Rules RAG system has completed Phase 1 and Phase 2 Stage 1, but has 6 outstanding items blocking full readiness. These include: a V2 API that's built but not exposed, dead code in the workflow graph, a minimal tool interface blocking Stage 2, and missing retrieval enhancement logic. This plan resolves them in priority order with TDD.

---

## Execution Order

```
Sprint 1: Item 2 (test safety) → Item 1 (mount V2 API)
Sprint 2: Item 3 (expand BaseTool)
Sprint 3: Item 4 (wire retry route in V2 graph)
Sprint 4: Item 6 (QueryRewriter for targeted retrieval)
Sprint 5: Item 5 (README update)
```

---

## Sprint 1: Test Safety + Mount V2 API ✅

### Item 2 — Harden tests against external services

**New file:** `tests/conftest.py`

- [x] autouse fixture to strip LLM_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY
- [x] Ensures all LLM clients remain None → heuristic fallback always fires

**Verify:** `pytest tests/ -v` — all existing tests should pass.

### Item 1 — Mount V2 API at `/v2` prefix

**Edit:** `app/main.py`
- [x] Add import: `from app.api import chat_v2`
- [x] Add router: `app.include_router(chat_v2.router, prefix="/v2", tags=["chat-v2"])`

**New file:** `tests/test_chat_v2_api.py`
- [x] Test `GET /v2/health` returns 200
- [x] Test `POST /v2/chat` returns 200 (runs workflow gracefully without index)
- [x] Test V1 `GET /health` still works (backward compat)
- [x] Test root `/` unchanged

**Verify:** `pytest tests/test_chat_v2_api.py -v` ✅

---

## Sprint 2: Expand BaseTool Interface ✅

### Item 3 — Tool infrastructure for Stage 2

**New file:** `app/schemas/tool.py`
- [x] `ToolCall` — Pydantic model: `call_id` (auto uuid), `tool_name`, `inputs: Dict`
- [x] `ToolResult` — Pydantic model: `call_id`, `tool_name`, `success: bool`, `output: Optional[Dict]`, `error: Optional[str]`

**Edit:** `app/tools/base_tool.py` (currently 14 lines → ~80 lines)
- [x] Add abstract property: `description -> str`
- [x] Add abstract property: `input_schema -> Dict[str, Any]` (JSON Schema format)
- [x] Add method: `validate_inputs(inputs) -> List[str]` (checks required fields + types against input_schema)
- [x] Add class: `ToolRegistry` with `register(tool)`, `get(name) -> Optional[BaseTool]`, `list_tools() -> List[dict]`

**New file:** `tests/test_tools.py`
- [x] Concrete `MockCalculatorTool` implementing all abstract methods
- [x] Tests: name, description, input_schema, validate_inputs (valid/missing/wrong type), run
- [x] Tests: ToolRegistry register/get/list/duplicate-raises
- [x] Tests: ToolCall/ToolResult schema creation

**Verify:** `pytest tests/test_tools.py -v` ✅

---

## Sprint 3: Wire Retry Route in V2 Graph ✅

### Item 4 — Activate `should_retry_route` dead code

**Edit:** `app/agents/graph_state.py`
- [x] Add field: `route_retry_count: int`

**Edit:** `app/agents/langgraph_workflow_v2.py`
- [x] Update `should_retry_route`: add retry count cap (`retry_count >= 1` → fallback)
- [x] Add `heuristic_fallback_node`: runs `PlannerAgent` heuristic, produces `RouteDecision` with `fallback_used=True`
- [x] Add `decompose_router_node`: no-op pass-through (convergence point for conditional routing)
- [x] Update `llm_route_planner_node`: increment `route_retry_count` in return dict
- [x] Rewire `build_graph`: route_validator → should_retry_route → {retry, fallback, continue}
- [x] Update `process_query` initial state: add `"route_retry_count": 0`

**New file:** `tests/test_retry_route.py`
- [x] Unit tests for `should_retry_route`: no validation → continue, valid → continue, should_retry → retry, should_fallback → fallback, retry exhausted → fallback
- [x] Integration test: query that would trigger conflicts still produces valid result

**Verify:** `pytest tests/test_retry_route.py tests/test_integration_v2.py -v` ✅

---

## Sprint 4: QueryRewriter for Targeted Retrieval ✅

### Item 6 — Use coverage gaps to rewrite second-pass queries

**New file:** `app/agents/query_rewriter.py`
- [x] `QueryRewriter.rewrite(original_query, missing_information) -> List[str]`
- [x] Strategy: use missing sub-task strings directly as queries; extract and preserve rule numbers; deduplicate; cap at 3 queries
- [x] No LLM dependency (pure heuristic: regex + string ops)

**Edit:** `app/agents/langgraph_workflow.py` — `second_retrieval_node`
- [x] Import and use `QueryRewriter`
- [x] Read `coverage_assessment.missing_information` from state
- [x] Call `rewriter.rewrite(query, missing_info)` to get targeted queries
- [x] Retrieve for each targeted query (instead of one original query)
- [x] Deduplicate new chunks by `chunk_id`

**New file:** `tests/test_query_rewriter.py`
- [x] Tests: rewrite from missing subtasks, empty missing returns original, extracts rule numbers, deduplicates, caps at 3

**Verify:** `pytest tests/test_query_rewriter.py -v` then `pytest tests/ -v` ✅

---

## Sprint 5: Documentation ✅

### Item 5 — Update README for V2

**Edit:** `README.md`
- [x] Add "V2 API" section after "API Endpoints": describe `/v2/health`, `/v2/chat`
- [x] Explain V2 architecture (LLM route planner → validator → retry/fallback → decomposer → retriever → ...)
- [x] List additional V2 response fields (route_decision, decomposition_plan, etc.)
- [x] Update project structure tree to include V2 files
- [x] Add usage examples for V2 endpoint

**Verify:** Read through, ensure accuracy vs. actual implementation. ✅

---

## File Change Summary

| File | Action | Sprint | Status |
|------|--------|--------|--------|
| `tests/conftest.py` | **New** | 1 | ✅ |
| `tests/test_chat_v2_api.py` | **New** | 1 | ✅ |
| `app/main.py` | Edit (2 lines) | 1 | ✅ |
| `app/schemas/tool.py` | **New** | 2 | ✅ |
| `app/tools/base_tool.py` | Edit (expand) | 2 | ✅ |
| `tests/test_tools.py` | **New** | 2 | ✅ |
| `app/agents/graph_state.py` | Edit (+1 field) | 3 | ✅ |
| `app/agents/langgraph_workflow_v2.py` | Edit (rewire graph) | 3 | ✅ |
| `tests/test_retry_route.py` | **New** | 3 | ✅ |
| `app/agents/query_rewriter.py` | **New** | 4 | ✅ |
| `app/agents/langgraph_workflow.py` | Edit (second_retrieval_node) | 4 | ✅ |
| `tests/test_query_rewriter.py` | **New** | 4 | ✅ |
| `README.md` | Edit | 5 | ✅ |

**Total: 7 new files, 6 edited files — ALL COMPLETE**

---

## Verification (End-to-End) ✅

```bash
# Full test suite — all green
pytest tests/ -v    # 195 passed, 0 failed

# V2 API accessible at /v2/*
# V1 backward compat maintained at /*
```
