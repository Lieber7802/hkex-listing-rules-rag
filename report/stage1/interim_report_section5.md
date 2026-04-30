# 5. Preliminary Performance Analysis

## 5.1 Experimental Setup

This section reports early-stage feasibility testing, not a comprehensive benchmark evaluation. The goal is to verify that the core pipeline works end-to-end and produces reasonable outputs.

**Table 5: Experimental Environment**

| Component | Specification |
|---|---|
| OS | Windows 11 |
| CPU | Intel Core i7 / AMD Ryzen 7 (or equivalent) |
| RAM | 16 GB |
| GPU | Not required (CPU inference for embeddings) |
| Python | 3.13.5 |
| Backend | FastAPI 0.135.1, Uvicorn 0.41.0 |
| Workflow | LangGraph 1.0.10, LangChain 1.2.10 |
| Lexical Index | rank-bm25 0.2.2 |
| Vector Index | FAISS 1.13.2 (faiss-cpu) |
| Embeddings | BGE-M3 via Ollama (localhost:11434) |
| LLM Client | OpenAI SDK 2.26.0 (DeepSeek Reasoner API) |
| Validation | Pydantic 2.11.7 |
| Testing | pytest 8.3.4 |
| Test Documents | HKEX Main Board Listing Rules excerpts (Chapters 14, 14A, selected guidance letters) |

The test document set consists of excerpts rather than the full consolidated rulebook. This is sufficient for validating the pipeline but does not represent the scale of a production deployment.

## 5.2 Functional Verification

We maintain 68 unit and integration tests across 8 test files. These cover the following modules:

**Table 6: Test Coverage Summary**

| Test File | Module | Tests | Status |
|---|---|---|---|
| `test_chunker.py` | Structure-aware chunking | 12 | Pass |
| `test_cleaner.py` | Text cleaning | 6 | Pass |
| `test_hybrid_retrieval.py` | BM25 + Dense + Fusion | 14 | Pass |
| `test_planner.py` | Query classification | 8 | Pass |
| `test_planner_refactor.py` | LLM route planner + validators | 14 | Pass |
| `test_chat_api.py` | API endpoint | 4 | Pass |
| `test_stage1_agentic_components.py` | Agentic components | 6 | Pass |
| `test_integration_v2.py` | End-to-end workflow | 4 | Pass |

Key verifications include: (1) documents are ingested and chunks are generated with correct metadata fields, (2) BM25 and FAISS indexes build without errors, (3) the hybrid retriever returns ranked results with fused scores, (4) the API endpoint accepts queries and returns structured JSON responses, and (5) citations in the output are traceable to specific chunk IDs and rule numbers.

## 5.3 Preliminary Query Case Study

To demonstrate the system's behavior, we tested three representative queries. Table 7 shows the results.

**Table 7: Query Case Study Results**

| # | Query | Type | Retrieved Evidence | Answer Summary | Citations |
|---|---|---|---|---|---|
| Q1 | "What is Rule 14A.35?" | Direct | Chunk containing Rule 14A.35 full text (score: 0.92) | Explains that Rule 14A.35 requires listed issuers to disclose connected transactions in annual reports, including details of the transaction and confirmation of compliance | Rule 14A.35, Chapter 14A |
| Q2 | "What are the disclosure requirements for connected transactions and how do they differ from notifiable transactions?" | Multi-hop | 4 chunks: Rule 14A.35, Rule 14A.46, Rule 14.34, Rule 14.41 (scores: 0.88, 0.81, 0.79, 0.72) | Compares disclosure requirements: connected transactions require independent shareholder approval and annual report disclosure; notifiable transactions require announcements based on size test ratios | Rule 14A.35, 14A.46, 14.34, 14.41 |
| Q3 | "How do I calculate the size test percentage ratios?" | Tool-dependent | 2 chunks: Rule 14.07 definitions, Rule 14.04 (scores: 0.85, 0.71) | Lists the five percentage ratios (assets, profits, revenue, consideration, equity) with definitions, but notes that actual calculation requires financial data not available to the system | Rule 14.07, 14.04; Uncertainty Note added |

**Q1 (Direct lookup):** The system correctly retrieves the specific rule and generates a concise summary. BM25 contributes strongly here because the rule number is an exact match.

**Q2 (Multi-hop):** The planner correctly classifies this as `multi_hop` and decomposes it into two sub-queries. The system retrieves relevant chunks from both Chapter 14A and Chapter 14, and the reasoning agent produces a comparative answer. However, the comparison could be more structured with clearer contrasts.

**Q3 (Tool-dependent):** The system retrieves the correct rule definitions but correctly flags that it cannot perform the actual calculation without financial input data. The uncertainty note is an honest acknowledgment of system limitations.

## 5.4 Preliminary Analysis

Based on the case study and functional testing, we observe the following:

**What works well:**
- Direct clause retrieval is reliable. When a query mentions a specific rule number, BM25 almost always retrieves the correct chunk.
- Citations are accurate. Every claim in the generated answer maps to a specific chunk ID and rule number.
- Response time is acceptable for a prototype: typically 3-8 seconds per query, with most time spent on LLM inference.

**What needs improvement:**
- The heuristic planner misclassifies some queries. For example, "What triggers a mandatory general offer?" is classified as `direct` but actually requires synthesizing information across multiple rules.
- Multi-hop answers are functional but lack depth. The reasoning agent sometimes provides a surface-level comparison rather than tracing the full logical chain across provisions.
- Evidence coverage is not verified. The system does not check whether the retrieved chunks actually cover all aspects of a multi-hop query before generating an answer.
- Ambiguous queries are not handled well. When a query could refer to multiple rule contexts, the system picks the highest-scoring chunks without asking for clarification.

These observations inform the Phase 2 improvements discussed in Section 6.
