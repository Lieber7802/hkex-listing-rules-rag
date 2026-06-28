# HKEX Listing Rules Compliance Agentic RAG System

Default documentation language: Chinese.

中文版本: [README.md](README.md)

This is a full-stack Agentic RAG system for Hong Kong Exchanges and Clearing Limited (HKEX) Listing Rules compliance Q&A. It uses FastAPI and LangGraph to orchestrate retrieval, evidence selection, tool execution, reasoning, and answer verification. It supports English and Chinese queries, with a React frontend and SSE streaming.

## Current Status

- Backend: FastAPI with V1 and V2 chat APIs.
- Frontend: React + TypeScript + Vite with streaming chat and an evidence panel.
- Retrieval: parallel BM25 + dense embedding retrieval, fused with RRF.
- Embeddings: local Ollama embeddings with resumable cache and batch embedding.
- Knowledge base: PDF, Markdown, and text ingestion; official HTML pages are converted to clean Markdown before ingestion.
- Tools: size test, transaction classifier, disclosure checklist, exact rule lookup, and automatic chaining.
- Tests: current full test suite contains 399 passing tests.

## Features

- **Compliance Q&A**: answers questions from HKEX Listing Rules, guidance, decisions, FAQs, and official materials.
- **Grounded citations**: responses include citations and pass through evidence selection and verification.
- **Hybrid retrieval**: BM25 and dense retrieval run in parallel and are fused by Reciprocal Rank Fusion.
- **Chinese support**: BM25, coverage checking, and verification use mixed English/CJK tokenization.
- **Multi-turn chat**: sessions are persisted and recent Q&A history is injected into context.
- **Computation tools**: supports size test calculation, transaction classification, disclosure checklist generation, and rule lookup.
- **Resumable vectorization**: embeddings are cached per chunk so interrupted indexing can continue.

## Project Structure

```text
app/
  api/                  FastAPI endpoints: /chat, /v2/chat, /v2/chat/stream
  agents/               LangGraph workflow, planner, retriever nodes, verifier
  core/                 config, logger, shared LLM client
  ingestion/            document loader, cleaner, structure-aware chunker
  retrieval/            Ollama embedder, BM25, hybrid retriever, index store
  schemas/              Pydantic request/response/document models
  services/             session persistence and history formatting
  tools/                size test, classifier, checklist, rule lookup
frontend/               React chat UI
scripts/                ingestion, index building, HKEX download/conversion tools
tests/                  unit and integration tests
data/
  raw/                  source documents and converted Markdown
  processed/            cleaned documents, gitignored
  chunks/               chunk JSON files, gitignored
  indexes/              FAISS, BM25 and embedding cache, gitignored
```

## Requirements

- Python 3.10+
- Node.js 18+
- Ollama for local embeddings
- DeepSeek or another OpenAI-compatible LLM API key

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install and build the frontend:

```bash
cd frontend
npm install
npm run build
```

Frontend development mode:

```bash
cd frontend
npm run dev
```

## Configuration

Configuration is loaded from `.env`. Key settings:

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | LLM provider |
| `LLM_MODEL` | `deepseek-v4-flash` | LLM model |
| `LLM_API_KEY` | empty | LLM API key |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible API base URL |
| `EMBEDDING_PROVIDER` | `ollama` | Embedding provider |
| `EMBEDDING_MODEL` | `qwen3-embedding:4b` | Ollama embedding model |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama base URL |
| `RETRIEVAL_TOP_K_BM25` | `20` | BM25 candidate count |
| `RETRIEVAL_TOP_K_DENSE` | `20` | dense candidate count |
| `RETRIEVAL_TOP_K_FINAL` | `10` | final RRF candidate count |
| `RRF_K` | `20` | RRF smoothing constant |

Pull the embedding model:

```bash
ollama pull qwen3-embedding:4b
```

## Knowledge Base Preparation

### 1. Add Source Files

Put official documents under `data/raw/`. Directly supported formats:

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

HTML files are not ingested directly. Downloaded HKEX HTML pages should first be converted to Markdown:

```bash
python scripts/convert_hkex_html_to_markdown.py
```

Converted files are written to:

```text
data/raw/html_converted/
```

Conversion audit logs are written to:

```text
data/raw/_download_manifests/
```

`DocumentLoader` skips internal directories such as `_download_manifests`, so download manifests and audit reports do not enter the knowledge base.

### 2. Ingestion

```bash
python scripts/ingest_documents.py
```

This creates:

```text
data/processed/
data/chunks/
```

### 3. Build Indexes

```bash
python scripts/build_index.py --embedding-workers 2 --embedding-batch-size 32 --progress-every 32
```

Indexes are saved under:

```text
data/indexes/
```

`data/processed/`, `data/chunks/`, and `data/indexes/` are gitignored and should not be pushed.

### Resumable Embedding

Each chunk embedding is cached under:

```text
data/indexes/_embedding_cache/
```

Check progress:

```bash
python scripts/build_index.py --cache-status
```

If indexing is interrupted, rerun the same build command. Cache keys include provider, model, chunk_id, and text content, so changed chunks are re-embedded automatically.

## Run the Server

```bash
uvicorn app.main:app --reload
```

Open:

- Web UI: http://localhost:8000
- Swagger: http://localhost:8000/docs

If the frontend is not built, the root path returns a backend status message. Run `cd frontend && npm run build` to serve the React UI through FastAPI.

## API

| Endpoint | Description |
| --- | --- |
| `GET /health` | V1 health check |
| `POST /chat` | V1 chat API |
| `GET /v2/health` | V2 health check |
| `POST /v2/chat` | V2 chat API with route/tool/evidence metadata |
| `POST /v2/chat/stream` | V2 SSE streaming API |
| `GET /v2/chat/stream?query=...` | EventSource-compatible streaming API |

Example:

```bash
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the disclosure requirements for a major transaction?"}'
```

Multi-turn chat:

```bash
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Rule 14A.35?"}'

curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What exemptions are available?", "conversation_id": "<conversation_id>"}'
```

## V2 Workflow

The current production workflow is `app/agents/langgraph_workflow_v2.py`:

```text
planner_agent_v2
  -> should_route
    -> execute_tool
      -> tool_input_extraction
      -> tool_executor
      -> tool_mode_router
        -> evidence_selector -> reasoning -> answer_verifier
        -> retriever -> coverage -> evidence_selector -> reasoning -> answer_verifier
    -> retriever
      -> coverage
      -> evidence_selector
      -> reasoning
      -> answer_verifier
```

Key V2 details:

- Uses heuristic `PlannerAgent` for intent and routing.
- LLM is used for tool input extraction and answer synthesis, not route planning.
- Tool input extraction has three recovery layers: LLM extraction, regex fallback, and execution-time recovery.
- `tool_only` queries skip coverage checking.
- `AgentState` uses LangGraph accumulation for `retrieved_chunks`, `citations`, `retrieval_rounds`, `tool_calls`, and `tool_results`.
- Reconstructing retrieval results from state must preserve `bm25_score` and `dense_score`; otherwise coverage strategy selection becomes unreliable.

## Tool Chain

Core HKEX computation tools:

1. `size_test_calculator`: calculates assets, profits, revenue, consideration, and equity capital ratios.
2. `transaction_classifier`: classifies transactions and applies connected-party overrides.
3. `disclosure_checklist`: generates announcement, circular, shareholder approval, and disclosure requirements.
4. `rule_lookup`: returns exact rule text by rule number.

Automatic chain:

```text
size_test -> classifier -> checklist
```

## Retrieval and Indexing

- BM25 stores a pre-tokenized corpus and uses Chinese character bigrams.
- Dense embeddings default to Ollama `qwen3-embedding:4b`.
- BM25 and dense retrieval run in parallel.
- RRF uses default `k=20`.
- Vector index uses FAISS `IndexFlatIP`; embeddings are L2-normalized.
- Chunk IDs are made unique by the chunker to prevent incorrect vector-result lookup.

## Frontend

The React frontend provides:

- SSE streaming chat
- evidence panel
- tool call and tool result display
- conversation id continuity
- responsive layout

Stack:

- React 18
- TypeScript
- Vite
- Tailwind CSS
- lucide-react

## Tests

Run all tests:

```bash
pytest -v
```

Run a single file:

```bash
pytest tests/test_planner_refactor.py -v
```

Run a single test:

```bash
pytest tests/test_planner_refactor.py::TestPlannerAgent::test_classify_direct_simple_lookup -v
```

Tests do not require a live LLM or prebuilt indexes.

## Common Scripts

| Script | Purpose |
| --- | --- |
| `scripts/ingest_documents.py` | raw -> processed/chunks |
| `scripts/build_index.py` | chunks -> FAISS/BM25 indexes with embedding cache |
| `scripts/convert_hkex_html_to_markdown.py` | clean official HTML into Markdown |
| `scripts/build_hkex_p1_p2_manifest.py` | build P1/P2 download manifest |
| `scripts/download_hkex_p1_p2_recommended.py` | download recommended P1/P2 files |
| `scripts/download_hkex_archive_first_pass.py` | download archive first-pass files |
| `scripts/demo_queries.py` | run demo queries |

## License

This project is developed for the CityU CS6520 course project and research demonstration.
