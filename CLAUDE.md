# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HKEX Listing Rules Compliance Agentic RAG System — a backend API for querying Hong Kong Stock Exchange regulatory documents using retrieval-augmented generation with LangGraph agent orchestration.

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

# Start API server
uvicorn app.main:app --reload

# Run demo queries
python scripts/demo_queries.py
```

## Architecture

### Core Pipeline (Query → Response)

```
User Query
    → PlannerAgent      # Classifies query_type (direct/multi_hop), generates sub_queries
    → HybridRetriever   # BM25 + dense embedding fusion, returns RetrievalResult[]
    → ReasoningAgent     # Synthesizes answer from retrieved evidence
    → CitationFormatter  # Formats citations from used chunks
    → ChatResponse       # Structured response with citations
```

### Data Flow

1. **Ingestion**: `scripts/ingest_documents.py` loads from `data/raw/`, cleans, chunks, saves to `data/chunks/`
2. **Indexing**: `scripts/build_index.py` loads chunks, creates FAISS vector index + BM25 index, saves to `data/indexes/`
3. **Serving**: `app/main.py` initializes FastAPI, `Orchestrator` loads IndexStore, `POST /chat` processes queries

### Key Modules

| Module | Responsibility |
|--------|----------------|
| `app/agents/orchestrator.py` | Coordinates planner → retriever → reasoning → formatter |
| `app/agents/planner_agent.py` | Query classification, sub-query decomposition, routing decisions |
| `app/retrieval/hybrid_retriever.py` | Fuses BM25 (lexical) + embedding (semantic) retrieval |
| `app/retrieval/index_store.py` | Loads/persists FAISS + BM25 indexes from `data/indexes/` |
| `app/agents/reasoning_agent.py` | LLM-based answer synthesis using retrieved evidence |
| `app/schemas/` | Pydantic models: `QueryRequest`, `ChatResponse`, `Chunk`, `Citation` |

### Agent Workflow (LangGraph)

`app/agents/langgraph_workflow.py` defines a StateGraph with nodes:
- `planner_node` → `retriever_node` → conditional router
- Branches: `reason` (direct), `retrieve_again` (second retrieval), `end`
- State carried in `AgentState` TypedDict across nodes

### Phase 2 Components (in progress)

Phase 2 adds: `coverage_checker.py`, `evidence_selector.py`, `answer_verifier.py` for evidence-driven retrieval and verification. These are integrated in `langgraph_workflow_v2.py`.

## Configuration

Environment variables (set in `.env`):
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` — LLM settings
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_BASE_URL` — embedding settings
- Index/data paths configured in `app/core/config.py`

Ollama must be running locally for embeddings (`ollama pull bge-m3`).

## API

- `GET /health` — health check
- `POST /chat` — submit query, returns `ChatResponse` with `answer`, `citations[]`, `retrieved_chunks[]`, `planner_output`
- Swagger docs at `http://localhost:8000/docs`

## Development Workflow (Superpowers)

This project uses the **superpowers** skill system for agentic development. Relevant skills:

### Skill Invocation
**Before ANY response or action**, check if a skill applies using the `Skill` tool. If there's even a 1% chance a skill applies, invoke it. This includes clarifying questions — skill check comes first.

### TDD (Test-Driven Development)
**Required for all new features and bug fixes.** The iron law:
```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```
Cycle: RED (write failing test) → GREEN (minimal code to pass) → REFACTOR (clean up)

```bash
# Example TDD cycle
pytest tests/test_planner.py::test_specific_behavior -v  # RED: should FAIL
# Write minimal implementation
pytest tests/test_planner.py::test_specific_behavior -v  # GREEN: should PASS
# Refactor if needed, then commit
```

### Plan Execution
Implementation plans are saved to `docs/superpowers/plans/`. For multi-step plans:
- Use **subagent-driven-development** skill for same-session execution with two-stage review (spec compliance then code quality)
- Use **executing-plans** skill for parallel session execution
- Plans follow format: bite-sized tasks with checkbox (`- [ ]`) syntax

### Model Selection
- **Mechanical tasks** (isolated functions, clear specs, 1-2 files): use cheapest model
- **Integration tasks** (multi-file coordination): use standard model
- **Architecture/design/review tasks**: use most capable model
