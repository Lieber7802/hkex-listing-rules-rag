# 中期报告文字风格修改建议 - Section 5-7 (Humanized)

## Section 5: Preliminary Performance Analysis or Experiments

### 5.1 Experimental Setup

**\[真实原文]**

> This section reports early-stage feasibility testing, not a comprehensive benchmark evaluation. The goal is to verify that the core pipeline works end-to-end and produces reasonable outputs.

**\[去AI味修改建议]**

- **AI味特征：** "reports early-stage feasibility testing, not" (AI对比句式)；"produces reasonable outputs" (过于正式)。
- **研究生风格（去AI化）：**

> This section reports early-stage feasibility testing. It is not a comprehensive benchmark evaluation. The goal is to check that the core pipeline works end-to-end and produces reasonable outputs.

***

**\[真实原文]**

> The test document set consists of excerpts rather than the full consolidated rulebook. This is sufficient for validating the pipeline but does not represent the scale of a production deployment.

**\[去AI味修改建议]**

- **AI味特征：** "consists of excerpts rather than" (AI对比句式)；"does not represent the scale of" (过于正式)。
- **研究生风格（去AI化）：**

> The test document set consists of excerpts from the rulebook, not the full consolidated version. This is enough for validating the pipeline, but it does not represent the scale of a production deployment.

***

### 5.2 Functional Verification

**\[真实原文]**

> We maintain 68 unit and integration tests across 8 test files. These cover the following modules:

**\[去AI味修改建议]**

- **AI味特征：** "We maintain" (过于正式)。
- **研究生风格（去AI化）：**

> We have 68 unit and integration tests across 8 test files. These tests cover the following modules:

***

**\[真实原文]**

> Key verifications include: documents are ingested and chunks are generated with correct metadata fields, BM25 and FAISS indexes build without errors, the hybrid retriever returns ranked results with fused scores, the API endpoint accepts queries and returns structured JSON responses, and citations in the output are traceable to specific chunk IDs and rule numbers.

**\[去AI味修改建议]**

- **AI味特征：** 一个句子包含5个并列项，过于完美；"are traceable to" (过于正式)。
- **研究生风格（去AI化）：**

> Key verifications include:
>
> - Documents are ingested and chunks are generated with correct metadata fields
> - BM25 and FAISS indexes build without errors
> - The hybrid retriever returns ranked results with fused scores
> - The API endpoint accepts queries and returns structured JSON responses
> - Citations in the output can be traced back to specific chunk IDs and rule numbers

***

## Section 6: Milestones and Overall Schedule

### 6.1 Work Completed So Far

**\[真实原文]**

> Phase 1 focused on building a functional backend prototype. Our work can be summarized in three areas:

**\[去AI味修改建议]**

- **AI味特征：** "can be summarized in" (AI常用表达)。
- **研究生风格（去AI化）：**

> Phase 1 focused on building a functional backend prototype. Our work includes three main areas:

***

**\[真实原文]**

> Knowledge Base Construction: We built a document ingestion pipeline that loads, cleans, and chunks HKEX regulatory documents while preserving their hierarchical structure, The pipeline produces dual indexes: BM25 for lexical matching and FAISS with BGE-M3 embeddings for semantic retrieval.

**\[去AI味修改建议]**

- **AI味特征：** "while preserving their hierarchical structure" (AI常用while从句)；"produces dual indexes" (过于正式)。
- **研究生风格（去AI化）：**

> Knowledge Base Construction: We built a document ingestion pipeline that loads, cleans, and chunks HKEX regulatory documents. The pipeline preserves their hierarchical structure and builds two indexes: BM25 for lexical matching and FAISS with BGE-M3 embeddings for semantic retrieval.

***

**\[真实原文]**

> Agentic Retrieval & Reasoning: We implemented a LangGraph-based workflow with a heuristic planner, hybrid retriever, conditional router, and reasoning agent powered by DeepSeek Reasoner. The system classifies queries as direct or multi\_hop, triggers conditional second retrieval, and generates citation-grounded answers. We also developed Stage 1 enhancements including an LLM-driven route planner, task decomposer, and validation components.

**\[去AI味修改建议]**

- **AI味特征：** "powered by" (AI常用词)；"triggers conditional second retrieval" (过于技术化)；三个并列项过于工整。
- **研究生风格（去AI化）：**

> Agentic Retrieval & Reasoning: We implemented a LangGraph-based workflow with a heuristic planner, hybrid retriever, conditional router, and reasoning agent using DeepSeek Reasoner. The system classifies queries as direct or multi\_hop. It can trigger a second retrieval when needed and generates answers with citations. We also developed Stage 1 enhancements, including an LLM-driven route planner, task decomposer, and validation components.

***

**\[真实原文]**

> System Integration & Testing: We delivered a FastAPI backend with /health and /chat endpoints, supported by 68 unit and integration tests covering ingestion, retrieval, agentic nodes, and API functionality. Project documentation includes design specifications, usage guides, and this interim report.

**\[去AI味修改建议]**

- **AI味特征：** "supported by 68 unit and integration tests covering" (AI常用分词短语)；过于完美的并列。
- **研究生风格（去AI化）：**

> System Integration & Testing: We built a FastAPI backend with /health and /chat endpoints. We also wrote 68 unit and integration tests that cover ingestion, retrieval, agentic nodes, and API functionality. Project documentation includes design specifications, usage guides, and this interim report.

***

### 6.2 Project Schedule and Milestones

**\[真实原文]**

> We are moving from the Phase 1 prototype to Phase 2, where we focus on reasoning quality, specialized tools, and formal evaluation.

**\[去AI味修改建议]**

- **AI味特征：** "where we focus on" (AI常用where从句)；三个并列项过于工整。
- **研究生风格（去AI化）：**

> We are now moving from the Phase 1 prototype to Phase 2. In Phase 2, we will focus on reasoning quality, specialized tools, and formal evaluation.

***

## Section 7: Work to be Completed for the Next Report

### 7.1 Technical Improvements

**\[真实原文]**

> Following the schedule outlined in Table 4, the next phase addresses the limitations identified in Section 4.5 and Section 5.2. Here we outline the concrete implementation plan.

**\[去AI味修改建议]**

- **AI味特征：** "addresses the limitations identified in" (被动语态)；"Here we outline the concrete implementation plan" (AI常用开场白)。
- **研究生风格（去AI化）：**

> Following the schedule in Table 4, the next phase will address the limitations identified in Section 4.5 and Section 5.2. Below we describe the concrete implementation plan.

***

**\[真实原文]**

> Planner Enhancement: The current heuristic planner will be replaced with an LLM-driven intent classifier that can better distinguish between direct lookups, multi-hop reasoning, and tool-dependent queries. This includes integrating the task decomposer and validation components developed in Stage 1 into the main workflow.

**\[去AI味修改建议]**

- **AI味特征：** "will be replaced with" (被动语态)；"that can better distinguish between" (过于完美的从句)。
- **研究生风格（去AI化）：**

> Planner Enhancement: We will replace the current heuristic planner with an LLM-driven intent classifier. This classifier can better distinguish between direct lookups, multi-hop reasoning, and tool-dependent queries. We will also integrate the task decomposer and validation components from Stage 1 into the main workflow.

***

**\[真实原文]**

> Evidence Coverage Verification: A coverage checker is planned that verifies whether retrieved chunks actually address all aspects of a multi-hop query before generating an answer. This will reduce cases where the system produces incomplete or surface-level responses.

**\[去AI味修改建议]**

- **AI味特征：** "A coverage checker is planned that verifies" (被动语态)；"surface-level responses" (过于正式)。
- **研究生风格（去AI化）：**

> Evidence Coverage Verification: We plan to build a coverage checker that verifies whether retrieved chunks actually address all aspects of a multi-hop query before generating an answer. This should reduce cases where the system produces incomplete or shallow responses.

***

**\[真实原文]**

> Answer Verification: A post-generation verification step will check whether the generated answer is grounded in the retrieved evidence and flag potential hallucinations or unsupported claims.

**\[去AI味修改建议]**

- **AI味特征：** "A post-generation verification step will check" (被动语态)；"flag potential hallucinations" (过于正式)。
- **研究生风格（去AI化）：**

> Answer Verification: We will add a verification step after generation. It will check whether the generated answer is based on the retrieved evidence and flag any unsupported claims or potential hallucinations.

***

**\[真实原文]**

> Tool Integration: The tool interface will be implemented for specialized compliance tasks, starting with a Size Test Calculator that can compute percentage ratios from structured financial inputs, and a Rule Lookup Tool that can fetch specific provisions on demand.

**\[去AI味修改建议]**

- **AI味特征：** "will be implemented for" (被动语态)；过于完美的并列。
- **研究生风格（去AI化）：**

> Tool Integration: We will implement the tool interface for specialized compliance tasks. The first tool will be a Size Test Calculator that can compute percentage ratios from structured financial inputs. We will also build a Rule Lookup Tool that can fetch specific provisions on demand.

***

**\[真实原文]**

> Retrieval Improvements: The score fusion strategy will be upgraded from weighted linear combination to Reciprocal Rank Fusion (RRF), which is more robust to score distribution differences. Query rewriting and reranking will also be explored to improve retrieval precision for ambiguous queries.

**\[去AI味修改建议]**

- **AI味特征：** "will be upgraded from...to" (被动语态)；"which is more robust to" (AI常用which从句)。
- **研究生风格（去AI化）：**

> Retrieval Improvements: We will upgrade the score fusion strategy from weighted linear combination to Reciprocal Rank Fusion (RRF). RRF is more robust to score distribution differences. We will also explore query rewriting and reranking to improve retrieval precision for ambiguous queries.

***

### 7.2 Evaluation and Reporting Work

**\[真实原文]**

> Formal evaluation is essential for validating the system's performance in a regulatory compliance context.

**\[去AI味修改建议]**

- **AI味特征：** "is essential for validating" (过于正式)。
- **研究生风格（去AI化）：**

> Formal evaluation is important to validate the system's performance in a regulatory compliance context.

***

**\[真实原文]**

> Benchmark Dataset: A benchmark dataset with 20-30 annotated compliance questions will be constructed, covering direct lookups, multi-hop reasoning, and tool-dependent scenarios. Each question will include ground-truth answers and expected citations.

**\[去AI味修改建议]**

- **AI味特征：** "will be constructed, covering" (被动语态 + 分词短语)。
- **研究生风格（去AI化）：**

> Benchmark Dataset: We will construct a benchmark dataset with 20-30 annotated compliance questions. The dataset will cover direct lookups, multi-hop reasoning, and tool-dependent scenarios. Each question will include ground-truth answers and expected citations.

***

**\[真实原文]**

> Evaluation Metrics: Metrics will be implemented for retrieval recall (whether the correct chunks are retrieved), citation quality (whether citations are accurate and traceable), and answer correctness (whether the generated answer matches the ground truth). Response time and system reliability will also be measured.

**\[去AI味修改建议]**

- **AI味特征：** 一个句子包含三个括号解释，过于完美；"will be implemented for" (被动语态)。
- **研究生风格（去AI化）：**

> Evaluation Metrics: We will implement metrics for retrieval recall, citation quality, and answer correctness. Retrieval recall checks whether the correct chunks are retrieved. Citation quality checks whether citations are accurate and traceable. Answer correctness checks whether the generated answer matches the ground truth. We will also measure response time and system reliability.

***

**\[真实原文]**

> Baseline Comparison: The agentic RAG system will be compared against baseline approaches, including standard single-pass RAG and keyword-based search, to demonstrate the value of the agentic workflow.

**\[去AI味修改建议]**

- **AI味特征：** "will be compared against...to demonstrate" (被动语态)；"to demonstrate the value of" (AI常用表达)。
- **研究生风格（去AI化）：**

> Baseline Comparison: We will compare the agentic RAG system against baseline approaches, including standard single-pass RAG and keyword-based search. This comparison will show whether the agentic workflow actually improves performance.

***

**\[真实原文]**

> System Demonstration: A recorded demonstration will be prepared showing the system handling representative compliance queries, including cases where it correctly triggers second retrieval, uses tools, and flags uncertainty.

**\[去AI味修改建议]**

- **AI味特征：** "will be prepared showing" (被动语态 + 分词短语)；过于完美的三项并列。
- **研究生风格（去AI化）：**

> System Demonstration: We will prepare a recorded demonstration. It will show the system handling representative compliance queries, including cases where it triggers second retrieval, uses tools, and flags uncertainty.

***

**\[真实原文]**

> Final Report: The final report will include comprehensive results, error analysis using RAGAS \[9], and a discussion of the system's capabilities and limitations as a research prototype.

**\[去AI味修改建议]**

- **AI味特征：** 过于完美的三项并列。
- **研究生风格（去AI化）：**

> Final Report: The final report will include comprehensive results and error analysis using RAGAS \[9]. It will also discuss the system's capabilities and limitations as a research prototype.

***

## 总结：Section 5-7 主要AI味特征

### 高频AI句式（已修改）

1. **被动语态过多** → 改为主动语态 "We will..."
2. **"will be X-ed"** → "We will X"
3. **"A coverage checker is planned that"** → "We plan to build a coverage checker that"
4. **"can be summarized in"** → "includes"
5. **"while preserving"** → 拆成两句
6. **过于完美的三项并列** → 拆成多句

### 修改后的效果

- 大量被动语态改为主动语态
- 句子更短，更直接
- 减少了"AI味"的完美并列结构
- 保留了技术准确性

