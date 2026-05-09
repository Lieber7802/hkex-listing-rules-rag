# Agentic RAG for HKEX Listing Rules Compliance

A full-stack Agentic Retrieval-Augmented Generation (RAG) system for Hong Kong Stock Exchange (HKEX) Listing Rules compliance Q&A. Features include:

- **React chat frontend** with real-time SSE streaming
- **Multi-turn conversation** with session management and contextual query rewriting
- **Hybrid retrieval** (BM25 + dense embeddings with Reciprocal Rank Fusion)
- **Dual LangGraph workflows** — V1 (heuristic) and V2 (LLM-routed with validation)
- **Tool chain execution** — Size Test Calculator, Transaction Classifier, Disclosure Checklist, Rule Lookup
- **Citation-grounded answers** with evidence verification
- **Bilingual support** — English and Chinese queries

## Project Structure

```
project_root/
├── app/
│   ├── api/                    # FastAPI endpoints
│   │   ├── chat.py                  # V1 API (root path)
│   │   ├── chat_v2.py              # V2 API (/v2 prefix)
│   │   └── chat_v2_stream.py      # V2 SSE streaming endpoints
│   ├── agents/                 # LangGraph workflow and agent nodes
│   │   ├── graph_state.py               # LangGraph state schema
│   │   ├── langgraph_workflow.py        # V1 StateGraph orchestration
│   │   ├── langgraph_workflow_v2.py     # V2 LLM-routed orchestration
│   │   ├── streaming_workflow.py        # SSE streaming wrapper
│   │   ├── llm_route_planner.py         # LLM-based route planning (V2)
│   │   ├── route_validator.py           # Heuristic route validation (V2)
│   │   ├── task_decomposer.py           # Multi-hop query decomposition (V2)
│   │   ├── decomposition_validator.py   # Decomposition validation (V2)
│   │   ├── planner_agent.py             # Heuristic query classification
│   │   ├── reasoning_agent.py           # Answer synthesis (LLM + fallback)
│   │   ├── contextual_query_rewriter.py # Multi-turn context rewriting
│   │   ├── query_rewriter.py            # Targeted second retrieval rewriting
│   │   ├── coverage_checker.py          # Evidence coverage assessment
│   │   ├── evidence_selector.py         # Evidence dedup and ranking
│   │   ├── answer_verifier.py           # Claim verification
│   │   └── citation_formatter.py        # Citation formatting
│   ├── core/                   # Configuration and logging
│   ├── ingestion/              # Document loading, cleaning, chunking
│   ├── models/                 # Data models
│   │   └── conversation.py          # ConversationSession, ConversationTurn
│   ├── retrieval/              # Embedding, BM25, hybrid retrieval
│   ├── schemas/                # Pydantic request/response models
│   │   ├── query.py                 # QueryRequest, PlannerOutput
│   │   ├── response.py             # ChatResponse, HealthResponse
│   │   ├── planning.py             # RouteDecision, DecompositionPlan (V2)
│   │   ├── tool.py                  # ToolCall, ToolResult
│   │   ├── citation.py             # Citation model
│   │   └── document.py             # Document/Chunk models
│   ├── services/               # Business logic services
│   │   ├── session_store.py         # Thread-safe session persistence (JSONL)
│   │   └── history_formatter.py     # Conversation history formatting for LLM
│   ├── tools/                  # HKEX compliance tools
│   │   ├── base_tool.py             # BaseTool ABC + ToolRegistry
│   │   ├── size_test_calculator.py  # 5 HKEX size-test ratio calculations
│   │   ├── transaction_classifier.py # Classification from ratios
│   │   ├── disclosure_checklist.py  # Required disclosure items by tier
│   │   ├── rule_lookup.py           # Exact rule text lookup
│   │   └── tool_chain.py           # Auto-chaining: size_test → classifier → checklist
│   └── main.py                 # FastAPI application + frontend serving
├── frontend/                   # React chat interface
│   ├── src/
│   │   ├── components/              # UI components (Header, InputBar, Messages, etc.)
│   │   ├── hooks/                   # useChat hook (SSE streaming)
│   │   ├── services/                # API client
│   │   └── types/                   # TypeScript type definitions
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/
│   ├── raw/                    # Source documents
│   ├── processed/              # Cleaned documents
│   ├── chunks/                 # Chunk artifacts
│   ├── indexes/                # FAISS + BM25 indexes
│   └── sessions/               # JSONL session files (gitignored)
├── scripts/                    # CLI scripts (ingest, build_index, demo)
├── tests/                      # Unit and integration tests (30+ files)
├── docs/                       # Documentation
└── requirements.txt
```

## Environment Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- pip

### Backend Installation

```bash
pip install -r requirements.txt
```

### Frontend Installation

```bash
cd frontend
npm install
npm run build    # Production build (served by FastAPI)
```

For frontend development with hot reload:
```bash
cd frontend
npm run dev      # Starts Vite dev server on port 5173
```

### Configuration

Configuration is managed via environment variables (create a `.env` file in project root):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `deepseek` | LLM provider |
| `LLM_MODEL` | `deepseek-reasoner` | LLM model name |
| `LLM_API_KEY` | — | API key for LLM |
| `LLM_BASE_URL` | `https://api.deepseek.com` | LLM API base URL |
| `EMBEDDING_PROVIDER` | `ollama` | Embedding provider (ollama or sentence-transformers) |
| `EMBEDDING_MODEL` | `bge-m3` | Embedding model name |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `SESSION_TTL_MINUTES` | `60` | Conversation session TTL |
| `SESSION_MAX_TURNS` | `50` | Max turns per session |
| `SESSION_HISTORY_WINDOW` | `5` | Recent Q&A pairs injected into LLM context |

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

Place your HKEX Listing Rules documents in `data/raw/`. Supported formats:
- `.txt` - Plain text
- `.md` - Markdown
- `.pdf` - PDF (via PyMuPDF)

### 2. Ingest Documents

```bash
python scripts/ingest_documents.py
```

### 3. Build Indexes

```bash
python scripts/build_index.py
```

### 4. Start the Server

```bash
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000.
- API documentation: http://localhost:8000/docs
- Chat UI: http://localhost:8000 (requires `frontend/dist/` to be built)

### 5. Query the API

Using curl:
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the disclosure requirements for connected transactions?"}'
```

With multi-turn conversation:
```bash
# First turn (creates a new session)
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Rule 14A.35?"}'

# Follow-up turn (pass conversation_id from previous response)
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What about the exemptions?", "conversation_id": "<id-from-previous-response>"}'
```

### 6. Run Demo Queries

```bash
python scripts/demo_queries.py
```

## API Endpoints

### V1 Endpoints (Root)

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Service health check |
| `POST /chat` | Query using V1 workflow (heuristic planner) |

### V2 Endpoints (`/v2` prefix)

| Endpoint | Description |
|----------|-------------|
| `GET /v2/health` | V2 service health check |
| `POST /v2/chat` | Query using V2 workflow (LLM-routed, multi-turn) |
| `POST /v2/chat/stream` | Streaming SSE response with intermediate events |
| `GET /v2/chat/stream?query=...` | EventSource-compatible streaming endpoint |

### Request Format

```json
{
  "query": "What are the disclosure requirements for connected transactions?",
  "conversation_id": "optional-session-id"
}
```

If `conversation_id` is omitted, a new session is created. Pass it in subsequent requests to continue the conversation.

### Response Format

```json
{
  "query_type": "direct",
  "answer": "...",
  "citations": [...],
  "retrieved_chunks": [...],
  "uncertainty_note": null,
  "planner_output": {...},
  "coverage_assessment": {...},
  "verification_result": {...},
  "confidence_level": "high",
  "conversation_id": "uuid-session-id",
  "turn_number": 1,
  "route_decision": {...},
  "decomposition_plan": {...},
  "tool_calls": [...],
  "tool_results": [...]
}
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

## Architecture

### V1 Workflow (Heuristic)

```
User Query
  -> PlannerAgent (regex classification)
  -> HybridRetriever (BM25 + dense fusion via RRF)
  -> [Optional second retrieval if coverage gaps]
  -> CoverageChecker
  -> EvidenceSelector
  -> ReasoningAgent
  -> AnswerVerifier
  -> CitationFormatter
  -> ChatResponse
```

### V2 Workflow (LLM-Routed)

```
User Query + Conversation History
  -> ContextualQueryRewriter (multi-turn context injection)
  -> LLM Route Planner (intent, decomposition, tool decision)
  -> Route Validator (heuristic cross-check)
  -> [Retry / Fallback if validation conflicts]
  -> Task Decomposer (if multi-hop)
  -> Decomposition Validator
  -> [Tool Executor if calculation query]
  -> Hybrid Retriever
  -> Coverage Checker -> [optional second retrieval]
  -> Evidence Selector
  -> Reasoning Agent (with conversation context)
  -> Answer Verifier
  -> Response (with conversation_id + turn_number)
```

### Multi-turn Conversation

The system maintains conversation state across turns:

1. **SessionStore**: Thread-safe in-memory cache with JSONL file persistence. Sessions auto-expire after configurable TTL.
2. **ContextualQueryRewriter**: Rewrites follow-up queries (e.g., "What about the exemptions?") into self-contained queries using conversation history.
3. **History injection**: Recent Q&A pairs are injected into the reasoning agent's context for coherent multi-turn answers.

### Tool Chain

When a calculation query is detected, tools execute in sequence:
1. `size_test_calculator` - Computes 5 HKEX size-test ratios
2. `transaction_classifier` - Maps ratios to transaction classification + applicable rules
3. `disclosure_checklist` - Generates required disclosure items by classification tier
4. `rule_lookup` - Retrieves exact rule text from index

## Frontend

The React frontend provides a chat interface with:

- Real-time SSE streaming (tokens appear as generated)
- Multi-turn conversation with session persistence
- Evidence panel showing retrieved chunks and citations
- Progress indicators for workflow stages
- Responsive design via Tailwind CSS

### Tech Stack

- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- Server-Sent Events (streaming)

## Running Tests

```bash
# Run all tests
pytest -v

# Run a single test file
pytest tests/test_planner.py -v

# Run a specific test
pytest tests/test_planner.py::TestPlannerAgent::test_classify_direct_simple_lookup -v
```

Tests run without LLM or index dependencies (mocked).

## Technical Stack

- **Backend**: FastAPI, Pydantic, pydantic-settings
- **Agent Orchestration**: LangGraph (StateGraph workflow)
- **LLM**: DeepSeek Reasoner (via OpenAI-compatible API)
- **Embeddings**: BGE-M3 via Ollama (local deployment)
- **Vector Store**: FAISS
- **Lexical Retrieval**: BM25 (custom implementation with RRF fusion)
- **Frontend**: React 18, Vite, Tailwind CSS, TypeScript
- **Testing**: pytest, httpx

## License

This project is for educational purposes as part of CS6520 coursework.
