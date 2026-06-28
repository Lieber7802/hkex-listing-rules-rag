# AGENTS.md

HKEX Listing Rules Compliance Agentic RAG System — FastAPI backend for querying Hong Kong Stock Exchange regulatory documents. Supports English + Chinese.

## Prerequisites

```bash
# Ollama must be running locally for embeddings
ollama pull qwen3-embedding:4b

pip install -r requirements.txt
python scripts/ingest_documents.py   # raw → data/processed/ → data/chunks/
python scripts/build_index.py        # chunks → FAISS + BM25 → data/indexes/
```

## Commands

```bash
pytest -v                                    # full suite (no LLM/indexes needed)
pytest tests/test_planner.py -v              # single file
pytest tests/test_planner.py::TestPlannerAgent::test_classify_direct_simple_lookup -v

uvicorn app.main:app --reload               # API server
python scripts/demo_queries.py              # demo queries
```

## Architecture (V2, current production)

V2 LangGraph (8 nodes, 3 conditional edges — `langgraph_workflow_v2.py`):

```
planner_agent_v2 → should_route:
  execute_tool → tool_input_extraction → tool_executor → tool_mode_router:
    select (tool_only) → evidence_selector → reasoning → answer_verifier
    retrieve            → retriever → coverage → evidence → reason → verify
  retrieve → retriever → coverage [→ retriever loop] → evidence → reason → verify
```

**Key V2 differences from V1**: adds 4 HKEX computation tools with auto-chaining (size_test → classifier → checklist) and SSE streaming at `/v2/chat/stream`. No longer uses LLM-based route planning (removed in favor of heuristic `PlannerAgent` + LLM-only tool input extraction).

**V1** (`langgraph_workflow.py`): planner → retriever → coverage → evidence → reasoning → verify. Still active at `POST /chat`.

## Critical Design Patterns

**LangGraph state accumulation**: `AgentState` (in `graph_state.py`) uses `Annotated[List[dict], add]` for `retrieved_chunks`, `citations`, `retrieval_rounds`, `tool_calls`, `tool_results` — these *accumulate* across nodes, not replace. Critical for second retrieval and tool result aggregation.

**Shared LLM client**: Single factory at `app/core/llm_client.py` via `get_llm_client()`. All agents and services import from here — do NOT create per-file LLM clients.

**Per-signal scores must survive serialization**: When reconstructing `RetrievalResult` from LangGraph state dicts, use `_reconstruct_results(chunks_data, index_store)` (defined in `langgraph_workflow_v2.py`) which preserves `bm25_score` and `dense_score`. Never hardcode `bm25_score=0.0` — this breaks `CoverageChecker` score-strategy selection.

**Hybrid retrieval**: BM25 + Dense embeddings run in parallel (`ThreadPoolExecutor(max_workers=2)`), fused via RRF with k=20.

**Chinese tokenization**: Both `CoverageChecker._text_overlap_score` and `AnswerVerifier._semantic_overlap` use `_tokenize_mixed()` (in `coverage_checker.py`) — English space-split + Chinese character bigrams. Never use plain `.split()` on mixed CJK text.

**Tool execution with recovery**: `tool_input_extraction_node.extract_tool_inputs()` tries LLM first, falls back to heuristic regex. `_execute_single_tool()` has a third recovery layer if validation still fails.

## Key Gotchas

- **BM25Index stores pre-tokenized corpus** in `tokenized_corpus` field — `build_index.py` must be re-run after any change to `_tokenize()`.
- **CoverageChecker score thresholds**: Uses `bm25_score` for `rule_lookup` intent, `dense_score` for `obligation_summary`, `fused_score` otherwise. If per-signal scores are lost during state serialization (see above), coverage assessment fails silently.
- **`tool_only` queries skip CoverageChecker** entirely — don't add coverage-dependent logic for tool-only paths.
- **`SizeTestCalculator` only requires 2 fields** (`transaction_consideration`, `transaction_type`) — other 8 fields default to 0. The input extractor tries to fill all 9, but confidence weights required fields at 70%.
- **`ChatResponse` no longer has** `decomposition_plan`, `route_validation`, or `decomposition_validation` fields (removed after V2 simplification).

## Key Modules

| Module | What it does |
|--------|-------------|
| `app/agents/langgraph_workflow_v2.py` | V2 graph: 8 nodes, `build_graph()`, `should_route()`, `tool_mode_router()` |
| `app/agents/planner_agent.py` | Heuristic: classifies 7 intents, splits sub-queries by and/or |
| `app/agents/tool_input_extraction_node.py` | LLM + heuristic tool parameter extraction |
| `app/agents/coverage_checker.py` | 3-signal matching + `_tokenize_mixed()` for CJK |
| `app/agents/evidence_selector.py` | `select_evidence()` function: dedup → sort by (has_rule, -score) → top N |
| `app/agents/answer_verifier.py` | Claim extraction, 3-type contradiction detection, confidence scoring |
| `app/agents/reasoning_agent.py` | LLM answer synthesis (max_tokens=1000, chunk truncation=800), fallback to template |
| `app/retrieval/hybrid_retriever.py` | Parallel BM25+dense → RRF fusion (k=20), `retrieve_for_sub_queries()` |
| `app/retrieval/bm25.py` | Own BM25 with pre-tokenized corpus + Chinese bigram tokens |
| `app/retrieval/embedder.py` | Ollama + SentenceTransformer embedders, raises on error (no silent zeros) |
| `app/tools/size_test_calculator.py` | 5-ratio calculator, 2 required fields |
| `app/tools/transaction_classifier.py` | 5-tier classification + connected party overrides |
| `app/tools/disclosure_checklist.py` | Checklist generator, items tagged with explicit `section` field |
| `app/tools/tool_chain.py` | Declarative chains: size_test → classifier → checklist |
| `app/core/llm_client.py` | **Single** shared LLM client factory — use everywhere |
| `app/schemas/planning.py` | `RouteDecision` (+ `to_planner_output()`), `ToolDecision`, simplified `SubTask` |
| `app/schemas/response.py` | `ChatResponse` — 3 deprecated fields removed |
| `app/services/session_store.py` | Thread-safe JSONL sessions, TTL=0 means never expire |

## Config

All settings in `app/core/config.py` (pydantic-settings, loads `.env`):
- LLM: `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` (default DeepSeek)
- Embedding: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_BASE_URL`
- Retrieval: `rrf_k` (20), `retrieval_top_k_bm25` (20), `retrieval_top_k_dense` (20), `retrieval_top_k_final` (10)

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | V1 readiness check |
| `POST /chat` | V1 query |
| `GET /v2/health` | V2 readiness check |
| `POST /v2/chat` | V2 query (returns `route_decision`, `tool_calls`, `tool_results`, etc.) |
| `POST /v2/chat/stream` | V2 SSE streaming |
| `GET /v2/chat/stream?query=...` | V2 EventSource browser streaming |

Swagger: `http://localhost:8000/docs`
