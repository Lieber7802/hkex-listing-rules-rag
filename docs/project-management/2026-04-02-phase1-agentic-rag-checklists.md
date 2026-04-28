# Phase 1 Agentic RAG Checklists

## 1. Scope Checklist

- [ ] Backend only
- [ ] Local execution only
- [ ] No frontend in Phase 1
- [ ] No `Size Test Calculator` in Phase 1
- [ ] No benchmark or RAGAS in Phase 1
- [ ] No production deployment concerns in Phase 1

## 2. Data Checklist

- [ ] Initial corpus list is explicitly defined
- [ ] Each source has a stable `document_id`
- [ ] Raw files are stored under `data/raw/`
- [ ] Cleaned text is stored under `data/processed/`
- [ ] Chunk artifacts are stored under `data/chunks/`
- [ ] Index files are stored under `data/indexes/`

## 3. Chunking Checklist

- [ ] Chunking preserves chapter information
- [ ] Chunking preserves section titles
- [ ] Chunking preserves rule numbers
- [ ] Chunk ids are deterministic
- [ ] Long sections have a fallback split strategy
- [ ] Citation can trace each chunk back to `source_path`

## 4. Retrieval Checklist

- [ ] BM25 retrieval works
- [ ] Dense retrieval works
- [ ] Scores are normalized before fusion
- [ ] Duplicate chunks are merged by `chunk_id`
- [ ] Final retrieval returns ranked top-k chunks

## 5. Planner Checklist

- [ ] Planner distinguishes `direct` and `multi_hop`
- [ ] Planner returns `sub_queries`
- [ ] Planner returns `needs_second_retrieval`
- [ ] Planner behavior is deterministic for demo queries

## 6. Reasoning Checklist

- [ ] Answer uses retrieved evidence only
- [ ] Answer includes citations
- [ ] Supporting clauses are exposed in response data
- [ ] Uncertainty is stated when evidence is weak
- [ ] No unsupported legal claim is generated intentionally

## 7. API Checklist

- [ ] `GET /health` exists
- [ ] `POST /chat` accepts a query payload
- [ ] Response includes `query_type`
- [ ] Response includes `answer`
- [ ] Response includes `citations`
- [ ] Response includes `retrieved_chunks`

## 8. Testing Checklist

- [ ] Cleaner tests pass
- [ ] Chunker tests pass
- [ ] Planner tests pass
- [ ] Retrieval tests pass
- [ ] API tests pass
- [ ] At least one `direct` demo query works
- [ ] At least one `multi_hop` demo query works

## 9. Documentation Checklist

- [ ] README explains environment setup
- [ ] README explains how to ingest documents
- [ ] README explains how to build indexes
- [ ] README explains how to run the server
- [ ] README explains how to test the API
- [ ] README describes Phase 2 extension points

## 10. Submission Checklist

- [ ] Deliverable scope matches Phase 1 rather than the full proposal
- [ ] Commands are reproducible on a local machine
- [ ] Example outputs contain citations
- [ ] Directory structure is clean and maintainable
- [ ] Phase 2 items are documented as future work, not missing work
