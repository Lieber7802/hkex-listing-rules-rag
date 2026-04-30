# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HKEX Listing Rules Compliance Agentic RAG System — a backend API for querying Hong Kong Stock Exchange regulatory documents using retrieval-augmented generation with LangGraph agent orchestration. Supports both English and Chinese queries (planner, coverage checker, and answer verifier all handle Chinese patterns).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Ingest documents (raw -> processed -> chunks)
python scripts/ingest_documents.py

# Build indexes (chunks -> FAISS + BM25)
python scripts/build_index.py

# Run tests
pytest -v

# Run a single test file
pytest tests/test_planner.py -v

# Run a single test
pytest tests/test_planner.py::TestPlannerAgent::test_classify_direct_simple_lookup -v

# Start API server (V1 workflow)
uvicorn app.main:app --reload

# Run demo queries
python scripts/demo_queries.py
```

## Architecture

### Core Pipeline (Query -> Response)

```
User Query
    -> PlannerAgent      # Classifies query_type (direct/multi_hop), generates sub_queries
    -> HybridRetriever   # BM25 + dense embedding fusion, returns RetrievalResult[]
    -> CoverageChecker   # Checks if retrieved chunks cover all sub-tasks
    -> EvidenceSelector  # Deduplicates, prioritizes rule-numbered chunks
    -> ReasoningAgent    # Synthesizes answer from retrieved evidence (LLM or fallback)
    -> AnswerVerifier    # Validates claims against evidence, detects contradictions
    -> CitationFormatter # Formats citations from used chunks
    -> ChatResponse      # Structured response with citations + confidence
```

### Two LangGraph Workflows

**V1** (`langgraph_workflow.py` / `LangGraphOrchestrator`): Active in production via `app/api/chat.py`.
```
planner -> retriever -> [second_retrieval?] -> coverage_checker -> evidence_selector -> reasoning -> answer_verifier
```
Uses heuristic `PlannerAgent` for query classification.

**V2** (`langgraph_workflow_v2.py` / `LangGraphOrchestratorV2`): Available via `app/api/chat_v2.py`, mounted at `/v2` prefix in `main.py`.
```
llm_route_planner -> route_validator -> [retry/fallback/continue] -> decompose_router -> [should_route 3-way]:
  decompose    → task_decomposer → decomposition_validator → retriever
  execute_tool → tool_executor → [tool_mode_router: select / retrieve]
  retrieve     → retriever
retriever → coverage_checker → evidence_selector → reasoning → answer_verifier
```
Adds LLM-based route planning with heuristic fallback, task decomposition for multi_hop queries, tool execution (4 HKEX tools), validation at each planning stage, and retry/fallback routing when validation detects conflicts.

### Data Flow

1. **Ingestion**: `scripts/ingest_documents.py` loads from `data/raw/` (recursive, supports .md/.txt/.pdf via PyMuPDF), cleans, chunks via `StructureAwareChunker`, saves to `data/chunks/`
2. **Indexing**: `scripts/build_index.py` loads chunks, creates FAISS vector index + BM25 index, saves to `data/indexes/`
3. **Serving**: `app/main.py` initializes FastAPI, orchestrator lazy-loads `IndexStore` on first request, `POST /chat` processes queries

### Key Architectural Patterns

**LangGraph state accumulation**: `AgentState` uses `Annotated[List[dict], add]` for `retrieved_chunks`, `citations`, `retrieval_rounds`, `tool_calls`, and `tool_results`. This means list fields *accumulate* across nodes rather than being replaced — critical when adding chunks from second retrieval rounds or tool results.

**LLM client lazy init with fallback**: `PlannerAgent`, `ReasoningAgent`, and `LLMRoutePlanner` all use `_get_client()` for lazy LLM initialization via OpenAI-compatible API. If the LLM is unavailable, each agent has a fallback path:
- `PlannerAgent`: heuristic regex classification (always available)
- `ReasoningAgent`: template-based answer from top chunk
- `LLMRoutePlanner`: falls back to `PlannerAgent` heuristics, sets `fallback_used=True`

**Global orchestrator singleton**: `app/api/chat.py` and `chat_v2.py` use module-level `orchestrator` with `get_orchestrator()` for lazy initialization.

### Key Modules

| Module | Responsibility |
|--------|----------------|
| `app/agents/langgraph_workflow.py` | V1 StateGraph: planner -> retriever -> coverage -> evidence -> reasoning -> verify |
| `app/agents/langgraph_workflow_v2.py` | V2 StateGraph: adds LLM route planning, task decomposition, validation stages |
| `app/agents/planner_agent.py` | Heuristic query classification via regex, intent detection with LLM fallback |
| `app/agents/llm_route_planner.py` | LLM-based route planning (V2), produces `RouteDecision` with tool decisions |
| `app/agents/task_decomposer.py` | Decomposes multi_hop queries into `SubTask` DAGs (V2) |
| `app/agents/query_rewriter.py` | Rewrites queries for targeted second retrieval using coverage gaps |
| `app/agents/coverage_checker.py` | Checks sub-task coverage using multi-signal matching (rule number, section title, text overlap) |
| `app/agents/evidence_selector.py` | Deduplicates and ranks chunks, prefers rule-numbered chunks, calculates diversity |
| `app/agents/answer_verifier.py` | Claim extraction, support verification, contradiction detection (numeric/conditional/scope) |
| `app/agents/reasoning_agent.py` | LLM-based answer synthesis or template fallback |
| `app/retrieval/hybrid_retriever.py` | Fuses BM25 (lexical) + dense embedding (semantic) via Reciprocal Rank Fusion (RRF, k=60) |
| `app/retrieval/index_store.py` | Loads/persists FAISS + BM25 indexes from `data/indexes/`, `get_chunks_by_rule_number` for exact rule lookup |
| `app/tools/base_tool.py` | `BaseTool` ABC (name, description, input_schema, validate_inputs, run) + `ToolRegistry` |
| `app/tools/size_test_calculator.py` | Calculates 5 HKEX size-test ratios, suggests transaction classification |
| `app/tools/transaction_classifier.py` | Maps ratio + type + connected → classification, rules, requirements |
| `app/tools/disclosure_checklist.py` | Generates structured disclosure checklist by classification tier |
| `app/tools/rule_lookup.py` | Exact-match rule text lookup via IndexStore |
| `app/tools/tool_chain.py` | Chain definitions: size_test → classifier → checklist auto-sequence |
| `app/agents/streaming_workflow.py` | `StreamingOrchestrator` wrapping `graph.stream()` → SSE events |
| `app/api/chat_v2_stream.py` | SSE streaming endpoints (POST + GET `/v2/chat/stream`) |
| `app/schemas/tool.py` | `ToolCall`, `ToolResult` Pydantic models |
| `app/schemas/query.py` | `QueryRequest`, `PlannerOutput` (includes tool_name, tool_mode) |
| `app/schemas/planning.py` | V2 schemas: `RouteDecision`, `DecompositionPlan`, `SubTask`, `ToolDecision`, validation results |
| `app/schemas/response.py` | `ChatResponse` (includes tool_calls, tool_results), `HealthResponse` |

### Schema Relationships

`PlannerOutput` (V1) is used by `PlannerAgent`, `CoverageChecker`, `EvidenceSelector`, and `ReasoningAgent`.
`RouteDecision` + `DecompositionPlan` (V2) are used by `LLMRoutePlanner`, `TaskDecomposer`, and V2 workflow nodes — which convert them back to `PlannerOutput` when calling shared components like `CoverageChecker`.

## Configuration

Environment variables (set in `.env`):
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` — LLM settings (default: DeepSeek)
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_BASE_URL` — embedding settings
- Retrieval: `rrf_k` (60, RRF smoothing constant), `retrieval_top_k_final` (10)
- All paths and settings centralized in `app/core/config.py` via `pydantic-settings`

Ollama must be running locally for embeddings (`ollama pull bge-m3`).

## API

- `GET /health` — V1 health check (returns `not_ready` if indexes not loaded)
- `POST /chat` — V1 query, returns `ChatResponse` with `answer`, `citations[]`, `retrieved_chunks[]`, `coverage_assessment`, `verification_result`, `confidence_level`
- `GET /v2/health` — V2 health check
- `POST /v2/chat` — V2 query (LLM-routed workflow), returns additional fields: `route_decision`, `decomposition_plan`, `route_validation`, `decomposition_validation`, `tool_calls`, `tool_results`
- `POST /v2/chat/stream` — V2 streaming SSE endpoint, yields events: `routing_complete`, `tool_executed`, `retrieval_complete`, `reasoning_started`, `answer_chunk`, `done`
- `GET /v2/chat/stream?query=...` — Same as above, EventSource browser-compatible
- Swagger docs at `http://localhost:8000/docs`

## Testing Patterns

Tests run without LLM or index dependencies. Key patterns:

- **`RetrievalResult` helper**: Tests construct `RetrievalResult` with inline `Chunk` objects (see `_result()` in `test_stage1_agentic_components.py`)
- **Disable LLM planner**: Pass `use_llm_planner=False` to `LangGraphOrchestratorV2` to force heuristic fallback in tests
- **V2 integration tests**: `test_integration_v2.py` tests the full V2 graph with heuristic fallback, checking `RouteDecision` and `DecompositionPlan` fields in results

## Development Workflow

**TDD is required for all new features and bug fixes.**
```
RED (write failing test) -> GREEN (minimal code to pass) -> REFACTOR (clean up)
```

Implementation plans are saved to `docs/superpowers/plans/` with checkbox (`- [ ]`) task format.
