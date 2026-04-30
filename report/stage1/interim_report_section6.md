# 6. Milestones and Overall Schedule

## 6.1 Work Completed So Far

Phase 1 focused on building a functional backend prototype. Our work can be summarized in three areas:

1. **Knowledge Base Construction**: We built a document ingestion pipeline that loads, cleans, and chunks HKEX regulatory documents while preserving their hierarchical structure (chapters, sections, rule numbers). The pipeline produces dual indexes: BM25 for lexical matching and FAISS with BGE-M3 embeddings for semantic retrieval.

2. **Agentic Retrieval & Reasoning**: We implemented a LangGraph-based workflow with a heuristic planner, hybrid retriever, conditional router, and reasoning agent powered by DeepSeek Reasoner. The system classifies queries as `direct` or `multi_hop`, triggers conditional second retrieval, and generates citation-grounded answers. We also developed Stage 1 enhancements including an LLM-driven route planner, task decomposer, and validation components.

3. **System Integration & Testing**: We delivered a FastAPI backend with `/health` and `/chat` endpoints, supported by 68 unit and integration tests covering ingestion, retrieval, agentic nodes, and API functionality. Project documentation includes design specifications, usage guides, and this interim report.

## 6.2 Project Schedule and Milestones

We are moving from the Phase 1 prototype to Phase 2, where we focus on reasoning quality, specialized tools, and formal evaluation.

**Table 8: Project Milestones**

| Phase | Milestone | Expected Completion | Status |
|---|---|---|---|
| Phase 1 | Background Research & Technology Selection | February 2025 | Completed |
| Phase 2 | Backend Prototype & Core Workflow | March 2025 | Completed |
| Phase 3 | LLM-driven Planner & Coverage Check | May 2025 | In Progress |
| Phase 4 | Tool Integration (Calculators) | June 2025 | Pending |
| Phase 5 | Benchmarking & RAGAS Evaluation | July 2025 | Pending |
| Phase 6 | Frontend & Production Prep | August 2025 | Pending |

We are currently working on upgrading the heuristic planner to an LLM-driven version and implementing a formal coverage check. Benchmarking will follow to ensure our answers meet regulatory standards.
