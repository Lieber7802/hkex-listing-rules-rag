# 7. Work to be Completed for the Next Report

## 7.1 Technical Improvements

Following the schedule outlined in Table 8, the next phase addresses the limitations identified in Section 4.5 and Section 5.4. Here we outline the concrete implementation plan.

**Planner Enhancement**: The current heuristic planner will be replaced with an LLM-driven intent classifier that can better distinguish between direct lookups, multi-hop reasoning, and tool-dependent queries. This includes integrating the task decomposer and validation components developed in Stage 1 into the main workflow.

**Evidence Coverage Verification**: A coverage checker is planned that verifies whether retrieved chunks actually address all aspects of a multi-hop query before generating an answer. This will reduce cases where the system produces incomplete or surface-level responses.

**Answer Verification**: A post-generation verification step will check whether the generated answer is grounded in the retrieved evidence and flag potential hallucinations or unsupported claims.

**Tool Integration**: The tool interface will be implemented for specialized compliance tasks, starting with a Size Test Calculator that can compute percentage ratios from structured financial inputs, and a Rule Lookup Tool that can fetch specific provisions on demand.

**Retrieval Improvements**: The score fusion strategy will be upgraded from weighted linear combination to Reciprocal Rank Fusion (RRF), which is more robust to score distribution differences. Query rewriting and reranking will also be explored to improve retrieval precision for ambiguous queries.

## 7.2 Evaluation and Reporting Work

Formal evaluation is essential for validating the system's performance in a regulatory compliance context.

**Benchmark Dataset**: A benchmark dataset with 20-30 annotated compliance questions will be constructed, covering direct lookups, multi-hop reasoning, and tool-dependent scenarios. Each question will include ground-truth answers and expected citations.

**Evaluation Metrics**: Metrics will be implemented for retrieval recall (whether the correct chunks are retrieved), citation quality (whether citations are accurate and traceable), and answer correctness (whether the generated answer matches the ground truth). Response time and system reliability will also be measured.

**Baseline Comparison**: The agentic RAG system will be compared against baseline approaches, including standard single-pass RAG and keyword-based search, to demonstrate the value of the agentic workflow.

**System Demonstration**: A recorded demonstration will be prepared showing the system handling representative compliance queries, including cases where it correctly triggers second retrieval, uses tools, and flags uncertainty.

**Final Report**: The final report will include comprehensive results, error analysis using RAGAS [12], and a discussion of the system's capabilities and limitations as a research prototype.
