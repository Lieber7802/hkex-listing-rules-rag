# Agentic RAG for HKEX Listing Rules Compliance

Phase 1 Backend Prototype

## Project Overview

This project implements an Agentic Retrieval-Augmented Generation (RAG) system for Hong Kong Stock Exchange (HKEX) Listing Rules compliance Q&A. Phase 1 delivers a local, testable backend prototype with:

- Document ingestion and structure-aware chunking
- Hybrid retrieval (BM25 + dense embeddings)
- LangGraph-based agent orchestration with planner and reasoning nodes
- Citation-grounded answer generation
- FastAPI interface

## Project Structure

```
project_root/
├── app/
│   ├── api/                # FastAPI endpoints
│   │   ├── chat.py              # V1 API (root path)
│   │   └── chat_v2.py           # V2 API (/v2 prefix)
│   ├── core/               # Configuration and logging
│   ├── ingestion/          # Document loading, cleaning, chunking
│   ├── retrieval/          # Embedding, BM25, hybrid retrieval
│   ├── agents/             # LangGraph workflow, planner, reasoning
│   │   ├── graph_state.py           # LangGraph state schema
│   │   ├── langgraph_workflow.py    # V1 StateGraph orchestration
│   │   ├── langgraph_workflow_v2.py # V2 LLM-routed orchestration
│   │   ├── llm_route_planner.py     # LLM-based route planning
│   │   ├── route_validator.py       # Heuristic route validation
│   │   ├── task_decomposer.py       # Query decomposition
│   │   ├── decomposition_validator.py # Decomposition validation
│   │   ├── query_rewriter.py        # Targeted query rewriting
│   │   ├── planner_agent.py         # Heuristic query classification
│   │   ├── reasoning_agent.py       # Answer generation
│   │   ├── coverage_checker.py      # Evidence coverage assessment
│   │   ├── evidence_selector.py     # Evidence dedup and ranking
│   │   ├── answer_verifier.py       # Claim verification
│   │   └── citation_formatter.py    # Citation formatting
│   ├── schemas/            # Pydantic data models
│   ├── tools/              # Tool interface (Stage 2 extension)
│   └── main.py             # FastAPI application
├── data/
│   ├── raw/                # Source documents
│   ├── processed/          # Cleaned documents
│   ├── chunks/             # Chunk artifacts
│   ├── indexes/            # Vector and BM25 indexes
│   └── demo/               # Sample queries
├── scripts/                # CLI scripts
├── tests/                  # Unit tests
├── docs/                   # Documentation
└── requirements.txt
```

## Environment Setup

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Configuration is managed via environment variables:

- LLM_PROVIDER: LLM provider (default: deepseek)
- LLM_MODEL: LLM model name (default: deepseek-reasoner)
- LLM_API_KEY: API key for LLM
- LLM_BASE_URL: LLM API base URL (default: https://api.deepseek.com)
- EMBEDDING_PROVIDER: Embedding provider, ollama or sentence-transformers (default: ollama)
- EMBEDDING_MODEL: Embedding model name (default: bge-m3)
- OLLAMA_BASE_URL: Ollama API base URL (default: http://localhost:11434)

Create a .env file in the project root to set these variables.

#### Ollama Setup (for local embeddings)

1. Install Ollama: https://ollama.ai
2. Pull the BGE model:
```bash
ollama pull bge-m3
```
3. Start Ollama server (usually runs automatically on port 11434)

#### DeepSeek Setup (for LLM)

1. Get API key from https://platform.deepseek.com
2. Set in .env file:
```
LLM_API_KEY=your-api-key-here
```

## Usage

### 1. Prepare Documents

Place your HKEX Listing Rules documents in data/raw/. Supported formats:
- .txt - Plain text
- .md - Markdown
- .pdf - PDF (basic support, interface ready for enhancement)

### 2. Ingest Documents

```bash
python scripts/ingest_documents.py
```

This will:
- Load documents from data/raw/
- Clean and normalize text
- Create structure-aware chunks
- Save to data/processed/ and data/chunks/

### 3. Build Indexes

```bash
python scripts/build_index.py
```

This will:
- Load chunks from data/chunks/
- Generate embeddings
- Build FAISS vector index
- Build BM25 lexical index
- Save to data/indexes/

### 4. Start the Server

```bash
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000.
API documentation: http://localhost:8000/docs

### 5. Query the API

Using curl:
```bash
curl -X POST "http://localhost:8000/chat" -H "Content-Type: application/json" -d "{\"query\": \"What are the disclosure requirements for connected transactions?\"}"
```

Using Python:
```python
import httpx
response = httpx.post("http://localhost:8000/chat", json={"query": "What is Rule 14A.35?"})
print(response.json())
```

### 6. Run Demo Queries

```bash
python scripts/demo_queries.py
```

## API Endpoints

### GET /health

Returns service health status.

Response:
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### POST /chat

Submit a compliance question.

Request:
```json
{
  "query": "What are the disclosure requirements for connected transactions?"
}
```

Response:
```json
{
  "query_type": "direct",
  "answer": "...",
  "citations": [...],
  "retrieved_chunks": [...],
  "uncertainty_note": null,
  "planner_output": {...}
}
```

## Running Tests

```bash
pytest -v
```

## V2 API (LLM-Routed Workflow)

The V2 API adds an LLM-based route planner with validation, task decomposition, and retry/fallback logic. It is accessible under the `/v2` prefix while V1 remains at root for backward compatibility.

### V2 Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /v2/health` | V2 service health check |
| `POST /v2/chat` | Query using V2 workflow (blocking JSON response) |
| `POST /v2/chat/stream` | Streaming SSE response with intermediate events |
| `GET /v2/chat/stream?query=...` | EventSource-compatible streaming endpoint |

### V2 Architecture

```
User Query
  -> LLM Route Planner (intent, decomposition, tool decision)
  -> Route Validator (heuristic cross-check)
  -> Retry / Fallback logic (max 1 retry, then heuristic fallback)
  -> Task Decomposer (if multi-hop)
  -> Decomposition Validator
  -> Hybrid Retriever
  -> Coverage Checker -> (optional targeted second retrieval)
  -> Evidence Selector
  -> Reasoning Agent
  -> Answer Verifier
  -> Response
```

Key differences from V1:
- **LLMRoutePlanner**: Uses LLM for intent classification and routing (falls back to heuristic)
- **RouteValidator**: Cross-checks LLM decisions against heuristic rules
- **TaskDecomposer**: Breaks complex queries into structured subtasks with dependencies
- **Retry/Fallback**: If route validation detects conflicts, retries LLM once, then falls back to heuristic

### V2 Response Fields

V2 responses include additional fields beyond V1:
- `route_decision` -- LLM routing decision with intent, decomposition flag, tool decision
- `decomposition_plan` -- Subtask breakdown for multi-hop queries
- `route_validation` -- Validation result with warnings and conflict detection
- `decomposition_validation` -- Subtask graph validation (cycle detection, completeness)
- `tool_calls` -- List of tool invocations (call_id, tool_name, inputs)
- `tool_results` -- List of tool execution results (success, output, error)

### Using V2

```bash
# Health check
curl http://localhost:8000/v2/health

# Query (blocking JSON)
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare disclosure requirements for connected and notifiable transactions"}'

# Streaming SSE (real-time events)
curl -N -X POST "http://localhost:8000/v2/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Rule 14.52?"}'
```

### SSE Event Types

When using the streaming endpoint, events are emitted as the workflow progresses:

| Event | Data | Description |
|-------|------|-------------|
| `routing_complete` | `{query_type, route_summary}` | Query routed successfully |
| `tool_executed` | `{tool_name, success, output_preview}` | Each tool in chain |
| `retrieval_complete` | `{num_chunks, top_score}` | Chunks retrieved |
| `reasoning_started` | `{}` | LLM reasoning begins |
| `answer_chunk` | `{content}` | Answer text (streamed) |
| `done` | `{total_time_ms, tools_executed}` | Workflow complete |

### Tool Chain

When a calculation query is detected, tools execute in chain:
1. `size_test_calculator` → computes 5 HKEX size-test ratios
2. `transaction_classifier` → maps ratio to classification + rules
3. `disclosure_checklist` → generates required actions checklist

## Phase 1 Scope

Phase 1 delivers:
- Backend prototype for local execution
- Document ingestion pipeline
- Structure-aware chunking
- Hybrid retrieval (BM25 + dense)
- Planner-based query routing
- Citation-grounded answers
- FastAPI interface

Phase 1 explicitly excludes:
- Web frontend
- Size Test Calculator tool
- Benchmark dataset
- RAGAS evaluation
- Production deployment

## Phase 2 Extension Points

The codebase is structured for future extensions:

- Tool Interface: app/tools/base_tool.py provides a base class for adding tools
- Evaluation Interface: The chunk and response schemas support evaluation frameworks
- Frontend-Friendly Response Schema: API responses are structured for direct consumption
- LLM Provider Abstraction: app/agents/reasoning_agent.py supports multiple LLM providers

## Technical Stack

- Backend: FastAPI, Pydantic
- Agent Orchestration: LangGraph (StateGraph workflow)
- LLM: DeepSeek Reasoner (via OpenAI-compatible API)
- Embeddings: BGE-M3 via Ollama (local deployment)
- Vector Store: FAISS
- Lexical Retrieval: BM25 (custom implementation)
- Testing: pytest, httpx

## License

This project is for educational purposes as part of CS6520 coursework.
