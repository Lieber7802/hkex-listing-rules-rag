# Phase 1 Agentic RAG Task Breakdown

## Workstreams

### Workstream A: Foundation

- [ ] Create Python project structure under `app/`, `scripts/`, `tests/`, and `data/`
- [ ] Add `requirements.txt`
- [ ] Add central config and logger modules
- [ ] Define shared schemas for document, chunk, query, citation, and response

### Workstream B: Knowledge Base Pipeline

- [ ] Implement local document loader for `.txt` and `.md`
- [ ] Add replaceable parser interface for `.pdf`
- [ ] Implement text cleaning with numbering preservation
- [ ] Implement structure-aware chunking
- [ ] Persist cleaned text and chunk artifacts to disk

### Workstream C: Retrieval Layer

- [ ] Implement embedding adapter
- [ ] Implement BM25 retrieval helper
- [ ] Implement local index persistence
- [ ] Implement hybrid retrieval score fusion and deduplication

### Workstream D: Agentic Flow

- [ ] Implement planner for `direct` vs `multi_hop`
- [ ] Implement sub-query generation
- [ ] Implement second-retrieval decision logic
- [ ] Implement evidence-grounded reasoning
- [ ] Implement citation formatter
- [ ] Implement orchestrator pipeline

### Workstream E: API and Demo

- [ ] Implement `GET /health`
- [ ] Implement `POST /chat`
- [ ] Add ingestion script
- [ ] Add index build script
- [ ] Add demo query script
- [ ] Prepare sample queries

### Workstream F: Quality and Documentation

- [ ] Add unit tests for cleaner
- [ ] Add unit tests for chunker
- [ ] Add unit tests for planner
- [ ] Add unit tests for hybrid retrieval
- [ ] Add API contract tests
- [ ] Write README with setup and run commands

## Suggested Execution Order

1. Finish Workstream A
2. Finish Workstream B
3. Finish Workstream C
4. Finish Workstream D
5. Finish Workstream E
6. Finish Workstream F

## Milestone Gates

### Milestone 1: Data Pipeline Ready

- [ ] Documents can be loaded
- [ ] Cleaned text artifacts are generated
- [ ] Chunks contain rule metadata

### Milestone 2: Retrieval Ready

- [ ] BM25 index builds successfully
- [ ] Dense index builds successfully
- [ ] Hybrid retrieval returns top-k results

### Milestone 3: Agentic QA Ready

- [ ] Planner returns stable routing output
- [ ] Reasoning produces citation-grounded answers
- [ ] Orchestrator connects planning, retrieval, and answer synthesis

### Milestone 4: Deliverable Ready

- [ ] API serves valid structured responses
- [ ] Demo queries run successfully
- [ ] README is complete
- [ ] Tests pass locally
