# Phase 1 Agentic RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, testable backend prototype for HKEX Listing Rules compliance QA with ingestion, structure-aware chunking, hybrid retrieval, planner-based orchestration, citation-grounded answering, and a FastAPI interface.

**Architecture:** The system uses LangGraph StateGraph for agent orchestration. Documents are normalized into stable schemas, chunked with legal structure preserved, indexed for both BM25 and dense search, then routed through a LangGraph workflow with planner, retriever, and reasoning nodes before returning structured citations.

**Tech Stack:** Python, FastAPI, Pydantic, LangGraph, sentence-transformers, FAISS, rank-bm25 or equivalent, pytest

---

## File Map

### Application files

- Create: `app/main.py`
- Create: `app/core/config.py`
- Create: `app/core/logger.py`
- Create: `app/api/chat.py`
- Create: `app/schemas/query.py`
- Create: `app/schemas/response.py`
- Create: `app/schemas/citation.py`
- Create: `app/schemas/document.py`
- Create: `app/ingestion/loader.py`
- Create: `app/ingestion/cleaner.py`
- Create: `app/ingestion/chunker.py`
- Create: `app/retrieval/embedder.py`
- Create: `app/retrieval/bm25.py`
- Create: `app/retrieval/hybrid_retriever.py`
- Create: `app/retrieval/index_store.py`
- Create: `app/agents/graph_state.py`
- Create: `app/agents/langgraph_workflow.py`
- Create: `app/agents/planner_agent.py`
- Create: `app/agents/reasoning_agent.py`
- Create: `app/agents/citation_formatter.py`
- Create: `app/agents/orchestrator.py`
- Create: `app/tools/base_tool.py`

### Script files

- Create: `scripts/ingest_documents.py`
- Create: `scripts/build_index.py`
- Create: `scripts/demo_queries.py`

### Data and docs

- Create: `data/raw/.gitkeep`
- Create: `data/processed/.gitkeep`
- Create: `data/chunks/.gitkeep`
- Create: `data/indexes/.gitkeep`
- Create: `data/demo/sample_queries.json`
- Create: `README.md`
- Create: `requirements.txt`

### Test files

- Create: `tests/test_cleaner.py`
- Create: `tests/test_chunker.py`
- Create: `tests/test_planner.py`
- Create: `tests/test_hybrid_retrieval.py`
- Create: `tests/test_chat_api.py`

## Task 1: Bootstrap Project Skeleton and Configuration

**Files:**

- Create: `app/core/config.py`
- Create: `app/core/logger.py`
- Create: `app/schemas/document.py`
- Create: `requirements.txt`

- [ ] Step 1: Create base folders and package markers
- [ ] Step 2: Define central settings for data paths, model names, top-k, and score weights
- [ ] Step 3: Add logging setup with simple console output
- [ ] Step 4: Define shared Pydantic document and chunk schemas
- [ ] Step 5: Install dependencies and verify imports

Run:

```bash
pip install -r requirements.txt
```

Expected:

- All dependencies install successfully
- Import smoke test passes

## Task 2: Implement Document Loading and Cleaning

**Files:**

- Create: `app/ingestion/loader.py`
- Create: `app/ingestion/cleaner.py`
- Test: `tests/test_cleaner.py`

- [ ] Step 1: Write failing tests for whitespace cleanup and numbering preservation
- [ ] Step 2: Implement local text and markdown loaders
- [ ] Step 3: Add a parser interface for future PDF support
- [ ] Step 4: Implement cleaner rules for repeated blank lines, broken spacing, and header/footer stripping
- [ ] Step 5: Persist cleaned text into `data/processed/`
- [ ] Step 6: Run targeted tests

Run:

```bash
pytest tests/test_cleaner.py -v
```

Expected:

- Rule numbers remain intact
- Cleaner removes obvious noise without collapsing structure

## Task 3: Implement Structure-Aware Chunking

**Files:**

- Create: `app/ingestion/chunker.py`
- Test: `tests/test_chunker.py`

- [ ] Step 1: Write failing tests for section-aware chunking and long-section fallback splitting
- [ ] Step 2: Implement parsing for chapter, section title, and rule number markers
- [ ] Step 3: Generate stable chunk ids and ordering metadata
- [ ] Step 4: Add fallback paragraph grouping for oversized sections
- [ ] Step 5: Save chunk JSON artifacts into `data/chunks/`
- [ ] Step 6: Run chunker tests

Run:

```bash
pytest tests/test_chunker.py -v
```

Expected:

- Chunk metadata is complete
- Chunk boundaries align with legal structure whenever possible

## Task 4: Build Dense and BM25 Indexing

**Files:**

- Create: `app/retrieval/embedder.py`
- Create: `app/retrieval/bm25.py`
- Create: `app/retrieval/index_store.py`
- Create: `scripts/build_index.py`

- [ ] Step 1: Implement chunk loading from JSON artifacts
- [ ] Step 2: Add embedding adapter with configurable model name
- [ ] Step 3: Build FAISS index for chunk vectors
- [ ] Step 4: Build BM25 index over chunk text
- [ ] Step 5: Persist both indexes and retrieval metadata into `data/indexes/`
- [ ] Step 6: Verify index build script runs end-to-end

Run:

```bash
python scripts/build_index.py
```

Expected:

- Index files are created
- Chunk metadata can be reloaded for retrieval

## Task 5: Implement Hybrid Retrieval

**Files:**

- Create: `app/retrieval/hybrid_retriever.py`
- Test: `tests/test_hybrid_retrieval.py`

- [ ] Step 1: Write failing tests for score fusion and deduplication
- [ ] Step 2: Implement BM25 retrieval method
- [ ] Step 3: Implement dense retrieval method
- [ ] Step 4: Normalize scores and merge by `chunk_id`
- [ ] Step 5: Return top-k ranked results with scores and metadata
- [ ] Step 6: Run retrieval tests

Run:

```bash
pytest tests/test_hybrid_retrieval.py -v
```

Expected:

- Shared chunks are merged correctly
- Returned candidates are stable and traceable

## Task 6: Implement Planner Agent

**Files:**

- Create: `app/agents/planner_agent.py`
- Test: `tests/test_planner.py`

- [ ] Step 1: Write failing tests for `direct` and `multi_hop` routing
- [ ] Step 2: Implement heuristic query classification rules
- [ ] Step 3: Generate sub-queries for `multi_hop` requests
- [ ] Step 4: Add `needs_second_retrieval` decision logic
- [ ] Step 5: Return a stable planner output schema
- [ ] Step 6: Run planner tests

Run:

```bash
pytest tests/test_planner.py -v
```

Expected:

- Planner output is deterministic for sample inputs
- Classification logic is explainable and inspectable

## Task 7: Implement Reasoning, Citation Formatting, and LangGraph Orchestration

**Files:**

- Create: `app/agents/graph_state.py`
- Create: `app/agents/langgraph_workflow.py`
- Create: `app/agents/reasoning_agent.py`
- Create: `app/agents/citation_formatter.py`
- Create: `app/agents/orchestrator.py`
- Create: `app/schemas/query.py`
- Create: `app/schemas/response.py`
- Create: `app/schemas/citation.py`

- [ ] Step 1: Define request and response schemas for chat
- [ ] Step 2: Define LangGraph AgentState TypedDict
- [ ] Step 3: Implement citation formatter from retrieved chunks
- [ ] Step 4: Implement reasoning flow that uses only retrieved evidence
- [ ] Step 5: Build LangGraph StateGraph with planner, retriever, reasoning nodes
- [ ] Step 6: Add conditional routing for second retrieval
- [ ] Step 7: Add an LLM adapter boundary without hard-binding one provider

Run:

```bash
python -c "from app.agents.langgraph_workflow import LangGraphOrchestrator; print('ok')"
```

Expected:

- LangGraphOrchestrator imports successfully
- Response schema supports citations and retrieved chunks

## Task 8: Build FastAPI Interface

**Files:**

- Create: `app/api/chat.py`
- Create: `app/main.py`
- Test: `tests/test_chat_api.py`

- [ ] Step 1: Write failing API contract tests for `POST /chat`
- [ ] Step 2: Implement `GET /health`
- [ ] Step 3: Implement `POST /chat` request handling
- [ ] Step 4: Connect API endpoint to orchestrator
- [ ] Step 5: Return structured response with citations and retrieved chunks
- [ ] Step 6: Run API tests

Run:

```bash
pytest tests/test_chat_api.py -v
```

Expected:

- API response matches schema
- Health endpoint confirms service readiness

## Task 9: Add Scripts, Demo Data, and README

**Files:**

- Create: `scripts/ingest_documents.py`
- Create: `scripts/demo_queries.py`
- Create: `data/demo/sample_queries.json`
- Create: `README.md`

- [ ] Step 1: Implement CLI ingestion script
- [ ] Step 2: Implement demo query runner
- [ ] Step 3: Add one `direct` and one `multi_hop` sample query
- [ ] Step 4: Document environment setup and run commands in README
- [ ] Step 5: Document Phase 2 extension points

Run:

```bash
python scripts/ingest_documents.py
python scripts/demo_queries.py
```

Expected:

- Demo scripts run without manual code edits
- README is sufficient for local reproduction

## Task 10: Verify the End-to-End Phase 1 Milestone

**Files:**

- Modify: `README.md`
- Verify: `tests/`

- [ ] Step 1: Run the full test suite
- [ ] Step 2: Run ingest command against sample data
- [ ] Step 3: Run index build command
- [ ] Step 4: Start FastAPI server
- [ ] Step 5: Execute one `direct` query and one `multi_hop` query
- [ ] Step 6: Confirm citations include source traceability
- [ ] Step 7: Update README with any command corrections

Run:

```bash
pytest -v
python scripts/ingest_documents.py
python scripts/build_index.py
uvicorn app.main:app --reload
```

Expected:

- Full local pipeline works
- Output satisfies the Phase 1 acceptance criteria

## Plan Self-Review

### Spec coverage

- Ingestion, cleaning, chunking: covered in Tasks 2 and 3
- Hybrid retrieval: covered in Tasks 4 and 5
- Planner and reasoning: covered in Tasks 6 and 7
- Citations and API: covered in Tasks 7 and 8
- Scripts and docs: covered in Tasks 9 and 10
- Phase 2 extension points: included in Tasks 1, 7, and 9

### Placeholder scan

- No `TODO` or `TBD` placeholders remain in the implementation sequence
- All major modules and test files are explicitly named

### Type consistency

- Shared chunk/document/query/response concepts are introduced before downstream usage
- Planner output fields and citation fields are consistent with the optimized design doc
