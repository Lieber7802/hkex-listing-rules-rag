# Phase 1 Agentic RAG Design Review and Optimized Spec

> Context: This document reconciles the original proposal with the Phase 1 `spec.md`, identifies weak points in the current spec, and defines an optimized and execution-ready design baseline for implementation.

## 1. Executive Summary

The current Phase 1 spec is directionally correct. It narrows the proposal from a full product into a minimal backend prototype, which is the right decision for a first course-project milestone. The main issue is not the high-level direction, but the lack of operational precision in several places: corpus boundary, ingestion contract, retrieval fusion method, planner decision rules, citation schema, and acceptance criteria.

This optimized design keeps the Phase 1 scope intentionally small:

- Backend only
- Local execution only
- A single orchestrated Agentic RAG flow
- Citation-grounded answers
- Explicit extension points for Phase 2

It also tightens the spec so implementation can proceed without repeated design backtracking.

## 2. Proposal vs. Phase 1 Alignment

The original proposal includes several items that are too large for a first implementation stage:

- Web UI
- `Size Test Calculator`
- Benchmark dataset construction
- RAGAS or other formal evaluation framework
- More complex multi-agent behavior

The current Phase 1 spec removes these items and focuses on the core backend pipeline. This is a good decomposition.

Recommended Phase split:

- Phase 1: backend prototype, ingestion, chunking, indexing, hybrid retrieval, planner, reasoning, citations, API
- Phase 2: frontend, tool system, calculator, benchmark/evaluation, comparative experiments, stronger orchestration

This separation should be stated explicitly in all project documents so the project is not judged against Phase 2 deliverables during Phase 1 review.

## 3. Review Findings on the Current Spec

### 3.1 What is already strong

- Scope is intentionally reduced to a minimum viable Agentic RAG
- The required modules are reasonably decomposed
- The spec correctly emphasizes structure-aware chunking
- Hybrid retrieval is a good fit for legal/regulatory text
- Citation-grounded responses are correctly treated as mandatory
- The spec leaves extensibility hooks for tools, evaluation, and frontend

### 3.2 Problems that should be fixed before implementation

1. Corpus boundary is too vague.

The spec says to focus on Notifiable Transactions, Connected Transactions, Size Tests, and related disclosure/reporting obligations, but it does not define the initial corpus set clearly enough for implementation and demo reproducibility.

Optimization:

- Define a small initial corpus list for Phase 1, for example 2 to 5 HKEX documents or extracts
- Record each source with `document_id`, source path, source type, import timestamp, and optional source URL
- Treat PDF support as preferred but not blocking; allow `.txt` and `.md` fallback for early validation

2. PDF ingestion requirement is under-specified.

The spec allows keeping PDF parsing as an interface, but the completion standard still says the system should import HKEX documents. This creates ambiguity about what counts as "done".

Optimization:

- Make ingestion support levels explicit:
- Level A: `.txt` / `.md` fully supported in Phase 1
- Level B: `.pdf` supported through a replaceable parser abstraction, with a basic implementation if feasible
- State that the pipeline must work end-to-end even if initial demo documents are converted text files

3. Chunking requirements are good but not fully operationalized.

The spec asks for structure-aware chunking, but does not define chunk boundaries, overlap policy, metadata completeness rules, or fallback behavior when rule markers are noisy.

Optimization:

- Primary split: chapter / section / rule number
- Secondary split: paragraph groups if a rule is too long
- Preserve `rule_number`, `section_title`, `chapter`, `parent_section`
- Add `chunk_order`, `char_start`, `char_end`, and `ingestion_version`
- Set a deterministic chunk id format such as `{document_id}:{rule_number}:{chunk_order}`

4. Hybrid retrieval is specified conceptually but not mechanically.

The spec says BM25 plus dense retrieval, but not how scores are fused, deduplicated, or capped.

Optimization:

- Use simple weighted score fusion in Phase 1
- Retrieve top `k_bm25` and top `k_dense`, normalize scores, merge by `chunk_id`
- Return top `k_final`
- Keep the fusion strategy configurable in `config.py`

5. Planner behavior is too abstract.

The spec asks for `direct` and `multi_hop`, but does not define how the classification is made or when second retrieval occurs.

Optimization:

- Use deterministic heuristics first, with optional LLM support behind an adapter
- `direct`: single obligation / clause lookup / single concept question
- `multi_hop`: query requires combining more than one rule, condition, or obligation
- `needs_second_retrieval = true` only if the first retrieval lacks evidence coverage for all sub-queries

6. Reasoning output is not constrained tightly enough.

Without stricter rules, the answer generator may hallucinate or over-summarize.

Optimization:

- Require every substantive claim in the answer to be supported by at least one retrieved chunk
- If evidence is partial, return an uncertainty note
- Keep answers concise and structured: short answer, rationale, citations, uncertainty

7. Citation schema is incomplete for debugging and frontend reuse.

Optimization:

- Each citation should include:
- `chunk_id`
- `document_id`
- `rule_number`
- `section_title`
- `chapter`
- `source_path`
- `snippet`
- `score`

8. Phase 1 acceptance criteria are too qualitative.

Optimization:

- Add explicit demo and smoke-test criteria:
- At least one ingestion command completes successfully
- At least one index-build command completes successfully
- API serves at least one `direct` query and one `multi_hop` query
- Responses include non-empty citations with traceable `source_path`

9. Configuration and provider abstraction need to be first-class requirements.

Optimization:

- Separate config for embedding model, LLM backend, storage paths, retrieval weights, and top-k values
- Do not bind code to one vendor
- Allow an offline or mocked path for tests

10. Evaluation is excluded, but basic verification is still needed.

Optimization:

- No benchmark system in Phase 1
- But include smoke tests and a small demo query set
- Store sample queries in `scripts/demo_queries.py` or `data/demo/`

## 4. Optimized Scope Statement

Phase 1 delivers a local Python backend prototype for HKEX Listing Rules compliance QA. The system ingests a small, curated corpus of regulatory text, cleans and structure-chunks the content, builds lexical and dense indexes, performs hybrid retrieval, routes queries through a simple planner, synthesizes answers from retrieved evidence, and returns structured citations through a FastAPI endpoint.

Phase 1 explicitly does not deliver:

- Web frontend
- Size Test Calculator
- Multi-agent autonomous system
- Benchmark platform
- RAGAS evaluation pipeline
- Production deployment, authentication, or observability stack

## 5. Optimized Architecture

### 5.1 Core flow

`User Query -> Planner -> Retriever -> Evidence Selector -> Reasoning Agent -> Citation Formatter -> API Response`

### 5.2 Design principles

- Keep every stage inspectable
- Prefer deterministic logic over opaque orchestration in Phase 1
- Preserve source structure for legal traceability
- Make every boundary replaceable for Phase 2

### 5.3 Recommended implementation choices

- Backend framework: FastAPI
- Data validation: Pydantic
- Dense retrieval: sentence-transformers embedding adapter
- Vector store: FAISS for local simplicity
- Lexical retrieval: BM25 via a lightweight Python library
- Planner: heuristic-first planner with optional LLM adapter
- Reasoning: provider-agnostic LLM wrapper plus deterministic fallback formatting

## 6. Optimized Module Contracts

### 6.1 Ingestion

Responsibilities:

- Load documents from local files
- Normalize extracted text into a standard internal document schema
- Persist raw and processed artifacts

Input contract:

- Supported in Phase 1: `.md`, `.txt`
- Optional basic `.pdf` parser behind loader abstraction

Output contract:

```json
{
  "document_id": "hkex-ct-001",
  "source_path": "data/raw/connected_transactions.md",
  "source_type": "md",
  "title": "Connected Transactions",
  "raw_text": "...",
  "metadata": {
    "imported_at": "2026-04-02T15:00:00Z"
  }
}
```

### 6.2 Cleaning

Responsibilities:

- Remove repeated headers/footers and noise
- Preserve legal numbering and headings
- Normalize whitespace without flattening structure

### 6.3 Chunking

Chunk schema:

```json
{
  "chunk_id": "hkex-ct-001:14A.35:0",
  "document_id": "hkex-ct-001",
  "chapter": "Connected Transactions",
  "section_title": "Reporting and announcement requirements",
  "rule_number": "14A.35",
  "parent_section": "Chapter 14A",
  "chunk_order": 0,
  "char_start": 0,
  "char_end": 864,
  "page_number": null,
  "source_path": "data/raw/connected_transactions.md",
  "text": "..."
}
```

Rules:

- Prefer semantic/legal boundaries over fixed token windows
- Only apply overlap when a section is too long
- Never destroy clause numbering

### 6.4 Retrieval

Phase 1 retrieval algorithm:

1. Run BM25 retrieval on chunk text
2. Run dense retrieval on the same chunk set
3. Normalize scores
4. Merge by `chunk_id`
5. Return ranked top-k candidates

Optional reranking is allowed only if implementation remains small and stable.

### 6.5 Planner

Planner output:

```json
{
  "query_type": "multi_hop",
  "sub_queries": [
    "What is the disclosure obligation?",
    "Which connected transaction rules apply?"
  ],
  "needs_second_retrieval": true,
  "reason": "Question combines rule identification with disclosure obligations"
}
```

### 6.6 Reasoning

Reasoning output should contain:

- `answer`
- `supporting_clauses`
- `uncertainty_note`
- `used_chunk_ids`

### 6.7 API

Recommended endpoint set for Phase 1:

- `POST /chat`
- `POST /ingest` optional if time allows
- `GET /health`

`POST /chat` response:

```json
{
  "query_type": "direct",
  "answer": "...",
  "citations": [
    {
      "chunk_id": "hkex-ct-001:14A.35:0",
      "document_id": "hkex-ct-001",
      "rule_number": "14A.35",
      "section_title": "Reporting and announcement requirements",
      "chapter": "Connected Transactions",
      "snippet": "...",
      "source_path": "data/raw/connected_transactions.md",
      "score": 0.88
    }
  ],
  "retrieved_chunks": ["..."],
  "uncertainty_note": null
}
```

## 7. Non-Functional Constraints for Phase 1

- Local run on a student machine
- Small corpus, not full-market coverage
- Reproducible scripts for ingestion and index build
- Basic tests for parser, chunker, retrieval merge, and API contract
- Clear logs and file outputs for debugging

## 8. Recommended Directory Structure

The structure in `spec.md` is broadly good. One refinement is to separate persistent artifacts more clearly:

```text
project_root/
├── app/
├── data/
│   ├── raw/
│   ├── processed/
│   ├── chunks/
│   ├── indexes/
│   └── demo/
├── scripts/
├── tests/
├── docs/
├── requirements.txt
└── README.md
```

## 9. Acceptance Criteria

Phase 1 is complete only if all of the following are true:

1. At least one HKEX-related source document can be ingested into normalized text artifacts.
2. The system can produce structured chunks with preserved rule metadata.
3. Dense and lexical indexes can be built locally.
4. Hybrid retrieval returns traceable chunks for a sample query.
5. Planner returns `direct` or `multi_hop` with deterministic rationale.
6. `POST /chat` returns an answer plus citations.
7. At least one demo `direct` query and one demo `multi_hop` query run successfully.
8. README documents environment setup, ingest, build-index, run-server, and demo commands.

## 10. Recommended Implementation Order

1. Data schema and config
2. Ingestion and cleaning
3. Structure-aware chunking
4. Index building
5. Hybrid retrieval
6. Planner
7. Reasoning and citation formatting
8. API
9. Tests and documentation

## 11. Final Recommendation

The spec should be implemented as a deliberately small, traceable, testable backend prototype. The key to a strong Phase 1 is not model sophistication, but engineering discipline around document structure preservation, evidence traceability, and reproducible commands. If those three foundations are solid, Phase 2 can safely add UI, tools, and evaluation without reworking the core architecture.
