# Agentic RAG Workflow Optimization Plan

## Problem Statement

The current Agentic RAG migration preserves the eight-node V2 graph, but several
state transitions are incomplete:

- coverage checks do not receive the planner intent;
- selected evidence is reported but not used by reasoning, citations, or answer
  verification;
- a coverage-triggered retry repeats the original retrieval instead of targeting
  the uncovered sub-tasks;
- retrieval rounds are not recorded;
- an injected `IndexStore` does not create a retriever, so the workflow reports
  itself as not ready;
- tests can accidentally load the developer's local index and call Ollama.

These defects make retrieval retries ineffective, allow the generated answer to
disagree with the evidence shown to the caller, and make test results depend on
the machine running them.

## Design Decisions

1. Keep the current eight-node graph. Do not restore the legacy V1
   `second_retrieval_node`.
2. Treat `iteration_count` as the number of retrieval invocations. The first
   retrieval uses the planner query or sub-queries; later invocations use
   coverage gaps.
3. Reuse the existing heuristic `QueryRewriter` for coverage-driven retries.
   Do not add an LLM call to retrieval rewriting.
4. On retry, return only chunks not already present in accumulated state and
   preserve fused, BM25, and dense scores.
5. Record each retrieval with the evaluation-compatible fields
   `round_number`, `queries`, `chunk_ids`, `coverage_before`, and
   `coverage_after`.
6. Make selected evidence the single evidence set used by answer synthesis,
   citation formatting, and answer verification. Fall back to all retrieved
   chunks only when no selection exists, such as tool-only paths.
7. Support dependency injection for an index, embedder, or retriever so tests
   can exercise real workflow routing without network access.
8. Isolate the test suite from `data/indexes` and external embedding services by
   default. Tests that need retrieval must provide an in-memory index and a
   deterministic embedder or retriever.

## Implementation Slices

### 1. Retrieval dependency construction

- Build `HybridRetriever` when an `IndexStore` is injected.
- Allow a caller to inject an embedder or a complete retriever.
- Preserve the existing disk-loading path for production.
- Verify readiness and one end-to-end retrieval with deterministic dependencies.

### 2. Intent-aware coverage

- Pass `planner_output.intent` into `CoverageChecker.assess`.
- Verify that an obligation-summary result with a strong dense score does not
  trigger an unnecessary second retrieval.

### 3. Evidence consistency

- Reconstruct the selected chunks from state through one shared helper.
- Use that evidence for reasoning, citations, and verification.
- Verify that citations contain only the chunks exposed as selected evidence.

### 4. Coverage-driven retry in the existing retriever node

- Use the normal planner query path on retrieval round one.
- On later rounds, read `retrieval_targets` from the latest coverage assessment,
  rewrite them with `QueryRewriter`, and retrieve each targeted query.
- Deduplicate retry results against accumulated chunk IDs.
- Stop at the existing `MAX_RETRIEVAL_ROUNDS` limit.
- Verify that the second call targets only missing information and adds new
  evidence instead of repeating round one.

### 5. Retrieval observability

- Store transient metadata for the current retrieval invocation in graph state.
- Complete the round record after coverage has been calculated.
- Verify round queries, chunk IDs, and before/after coverage values.

### 6. Test isolation and documentation

- Redirect the default test index path to a temporary empty directory.
- Replace external embedding lookup with a deterministic test embedder.
- Update the architecture diagram to describe the heuristic planner, current
  routing, evidence flow, and targeted retry behavior.
- Keep `/chat` and `/chat/stream` contracts unchanged.

## Verification

Each slice must pass its focused regression tests before proceeding. Completion
requires:

- all Agentic RAG workflow and API tests passing;
- the complete `pytest` suite passing without Ollama or a local index;
- Python source compilation succeeding;
- the frontend production build succeeding;
- a final code review finding no unresolved correctness issue.

## Out of Scope

- restoring the removed V1 or V2 API routes;
- reintroducing LLM route planning, route validation, or task decomposition;
- changing retrieval thresholds, RRF parameters, or embedding models;
- changing the public `ChatResponse` contract beyond populating existing fields
  correctly;
- modifying the frozen evaluation release data.
