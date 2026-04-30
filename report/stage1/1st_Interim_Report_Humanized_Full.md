# Agentic RAG for HKEX Listing Rules Compliance
## 1st Interim Report

**Student Name:** Li Yubo  
**Student ID:** 59903650  
**Supervisor:** Chen MA  
**Course:** CS6520  
**Date:** 2026.4.6

---

## 1. Introduction

### 1.1 Background and Problem Context

The Hong Kong Stock Exchange (HKEX) is one of the world's major financial markets, with over 2,600 listed companies and a market capitalization exceeding HKD 30 trillion as of 2025 [1]. Listed companies must comply with the HKEX Listing Rules. The Main Board Listing Rules include over 30 chapters and more than 2,500 individual provisions, along with many appendices and guidance materials [2]. The Growth Enterprise Market (GEM) uses a similar rulebook. HKEX also provides supplementary materials like Guidance Letters, Listing Decisions, and Frequently Asked Questions to help issuers interpret these rules [3].

These documents are heavily cross-referenced. To understand the requirements for a connected transaction, a company might need to check Chapter 14A (Connected Transactions), Chapter 14 (Notifiable Transactions), Chapter 2 (Definitions), and several guidance letters. Each rule often points to other sub-rules or exceptions. As a result, company secretaries and legal advisors often find it hard to locate all relevant provisions and reach a clear conclusion [4].

Traditional keyword search can find specific rules, but it fails when dealing with this complexity. It cannot understand legal terminology or handle multi-step reasoning. Identifying implicit cross-references between chapters is also difficult. Practitioners spend considerable time manually tracing these connections, which increases the risk of missing important obligations. So we need more intelligent tools for compliance questions. Retrieval-Augmented Generation (RAG) systems with agent planning capabilities could provide accurate and evidence-based answers.

### 1.2 Project Objectives

This project builds an Agentic Retrieval-Augmented Generation (RAG) system for HKEX Listing Rules compliance questions. Standard RAG systems usually retrieve information in a single pass, which is not enough for complex regulatory documents. Our system adds agentic planning and multi-step reasoning to better handle this complexity [5].

The primary objectives for Phase 1 are:

1. **Document Ingestion:** Import HKEX documents (Main Board, GEM, and guidance materials), perform structure-aware chunking that preserves rule numbers and chapter titles, and build a search index using both keyword (BM25) and semantic (embedding) methods [6].

2. **Agentic Workflow Prototype:** Build a workflow using LangGraph with three components: a Planner to classify questions, a retriever to find relevant information, and a reasoning component to synthesize answers. The system can handle both simple rule lookups and more complex questions that need to combine multiple rules [7].

3. **Citation-Grounded Answers:** Every answer is supported by evidence from the rules. Each answer includes clear citations with rule numbers and chapter titles. This is important for compliance tasks, where evidence needs to be verifiable [8].

4. **Backend API:** Develop a FastAPI backend with a modular architecture. This makes it easier to add new features later, such as specialized compliance tools, frontend interfaces, or evaluation datasets [9].

Phase 1 will not include: a web interface, specialized calculators, a full benchmark dataset, formal evaluation frameworks, or production-level deployment. We focus on building a functional backend prototype to validate our approach.

### 1.3 Practical Value and Expected Outcome

Compliance officers, company secretaries, and legal advisors often spend hours searching through multiple chapters and guidance documents. Our system automatically locates relevant rules, traces cross-references, and provides answers with citations. This saves time and helps reduce the risk of missing important regulatory obligations [10].

This project also investigates how information systems can reason about legal documents, rather than just matching keywords. It could lead to more advanced tools later, like automated disclosure checkers or systems that provide scenario-based advice [11].

Phase 1 aims to deliver:

1. **Functional Backend Prototype:** A Python application that can ingest HKEX documents, index them, and provide compliance answers via a RESTful API.

2. **Knowledge Pipeline:** A structured workflow that processes regulatory documents, preserves their hierarchy, and enables precise retrieval.

3. **Preliminary Validation:** Initial testing to prove that the system can handle both simple and multi-hop compliance questions and return answers backed by traceable sources.

4. **Architectural Foundation:** A modular design that allows for easy integration of new tools, frontends, and evaluation methods in the next phase [12].

---

## 2. Related Work

To understand how our system fits into the broader landscape of compliance question answering, we review four areas of related research: traditional information retrieval, neural retrieval methods, RAG systems, and agentic RAG approaches.

### 2.1 Traditional Information Retrieval for Regulatory Documents

Traditional information retrieval systems, like keyword-based search and the BM25 algorithm, are commonly used for regulatory document retrieval [13, 14]. These systems use inverted indexes to match user queries with terms in the documents.

The main advantage of these methods is their stability and speed. Because they are based on literal term matching, they provide high interpretability. Users can clearly see why a specific document was retrieved based on the occurrence of their search terms. For many legal and compliance tasks, this deterministic nature is a significant benefit, as it minimizes the risk of the system "hallucinating" relevance where none exists.

However, traditional IR systems have limitations in complex scenarios like the HKEX Listing Rules. For one, they lack semantic understanding. If a user queries "disclosure requirements for connected transactions," the system may fail to find relevant documents if they use synonyms or different terms that are not in the query. For another, they struggle with multi-hop questions. When a query requires synthesizing information from multiple chapters or cross-referencing different rule provisions, keyword-based systems cannot perform the necessary reasoning steps.

### 2.2 Neural and Dense Retrieval Methods

Dense retrieval methods try to solve these problems by representing queries and documents as vectors in a shared semantic space. Models like BERT [15] or specialized embedding models can capture the meaning of text even when different words are used. This allows the system to retrieve documents based on conceptual similarity rather than exact keyword matches.

In the legal domain, dense retrieval has shown promise for tasks like case law retrieval and statute search. However, it also has drawbacks. Dense models can sometimes retrieve documents that are semantically similar but not legally relevant. For example, a query about "connected transactions" might retrieve documents about "related party transactions" even if the legal definitions differ. This is why many systems now use hybrid approaches that combine keyword matching with semantic retrieval.

### 2.3 RAG and Agentic RAG Systems

RAG systems combine retrieval with generation. They use external retrieved evidence to generate answers [16]. This approach has become popular for question answering because it grounds the generated text in real documents, which reduces hallucination.

Agentic RAG is a move towards more autonomous systems [17]. Unlike a standard RAG pipeline, an Agentic RAG system uses a planner to break down a user's question, run multiple retrieval steps, and then synthesize the evidence. Recent research shows this approach works better for complex Q&A. It changes the system from a "one-shot" responder into one that can reason iteratively.

By separating planning, retrieval, and reasoning into different roles, these systems can check whether they have enough evidence before generating a final answer. If the agent determines that the evidence is insufficient or contradictory, it can choose to backtrack or rephrase the query. This degree of control is essential for accurate compliance advising, where a single missed provision can lead to incorrect guidance.

One implementation of this paradigm is LangGraph [18], a framework for building stateful workflows. LangGraph allows developers to define nodes (such as a planner, retriever, or reasoner) and edges (conditional transitions between nodes). This makes it easier to build systems that maintain context and make iterative decisions about what information is still needed.

### 2.4 Relationship Between Existing Work and This Project

Our system integrates both traditional and neural retrieval. We use a hybrid approach that combines BM25 for precise keyword matching and dense embeddings for semantic recall. This balances the need for lexical exactness with the ability to handle synonyms and paraphrased queries.

Beyond retrieval, our system extends standard RAG by introducing a planner and a conditional router. This allows the system to distinguish between simple rule lookups and multi-hop compliance questions. It triggers a second retrieval step only when necessary. Each answer includes citations with rule numbers and source document identifiers, which is a requirement for compliance use cases where answer provenance must be traceable.

That said, the current prototype has clear limitations. The planner relies on simple heuristic classification rather than full LLM-driven reasoning. The system does not yet support tool use (such as financial calculators), session memory, or formal evaluation. These are planned for Phase 2. At this stage, the system is best understood as a domain-specific Agentic RAG prototype for HKEX compliance. It is more capable than a standard single-pass RAG system, but still an early-stage implementation focused on validating the core agentic workflow.

---

## 3. System Modeling and Structure

Building on the approaches discussed in Section 2, this section defines the scope, architecture, and workflow of our system.

### 3.1 Problem Scope and System Boundary

This project focuses on a specific subset of the HKEX Listing Rules: Notifiable Transactions (Chapter 14), Connected Transactions (Chapter 14A), Size Tests (Rule 14.07 and related provisions), and associated disclosure obligations. We chose these areas because they appear frequently in compliance questions. They also require cross-referencing between multiple rule provisions.

**Table 1: System Input/Output Specification**

| Component | Description | Format |
|-----------|-------------|--------|
| Input | Natural language compliance question | JSON: {"query": "..."} |
| Output - Answer | Natural language response synthesizing relevant rules | string |
| Output - Citations | Rule numbers, chapter references, source identifiers | List[Citation] |
| Output - Evidence | Retrieved chunks used as supporting evidence | List[Chunk] |
| Output - Uncertainty | Note indicating incomplete or conflicting evidence | string or null |

For example, a user might ask: "What are the disclosure requirements for a connected transaction?" The system returns a structured JSON response containing all four output components.

### 3.2 Overall Architecture

The system follows a pipeline with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation. The overall architecture is shown in Figure 1.

**Figure 1 Required: System Architecture Diagram**

The first four modules run offline during document preparation. Document Ingestion supports plain text, Markdown, and PDF. PDF support is still basic in Phase 1. Cleaning normalizes text by removing excessive whitespace, fixing encoding issues, and standardizing line breaks.

Chunking preserves document structure. Instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers. Then it creates chunks that keep these elements intact. Indexing builds two retrieval indexes: BM25 for keyword search and FAISS for semantic search using BGE-M3 embeddings.

The last two modules run online during query time. Query Processing routes the user's question through the LangGraph workflow described in Section 3.3. Response Generation generates the answer using DeepSeek Reasoner and adds citations with rule numbers.

### 3.3 LangGraph Workflow Structure

Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph can do conditional branching based on intermediate results. The workflow is shown in Figure 2.

The workflow starts at the Planner Node. It classifies the query as direct (simple rule lookup) or multi_hop (requires combining multiple rules). For multi-hop queries, the Planner also breaks the question into sub-queries. Classification uses heuristic rules based on keyword patterns. It checks for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

The Retriever Node performs hybrid retrieval by querying both BM25 and FAISS indexes. It retrieves top-k chunks from each and normalizes scores to a [0, 1] range. Then retrieved chunks are stored in the workflow state.

The Conditional Router checks whether the retrieved evidence covers all sub-queries. For each sub-query generated by the Planner, the router checks whether at least one retrieved chunk has a relevance score above a minimum threshold (0.3 in Phase 1). If any sub-query lacks supporting evidence, the router sets needs_second_retrieval = True and sends the workflow to the Second Retrieval Node. For direct queries, the router always proceeds to reasoning.

The Second Retrieval Node performs another retrieval pass using the uncovered sub-queries as new search terms. Newly retrieved chunks are added to the state and deduplicated by chunk_id.

The Reasoning Node uses DeepSeek Reasoner to generate an answer based on all retrieved chunks. The prompt instructs the LLM to ground every claim in the retrieved evidence and include an uncertainty note if evidence is incomplete.

The Citation Formatter Node post-processes the answer to make sure citations are properly formatted with rule numbers, chapter references, and source document identifiers. The final structured response is returned to the user.

**Figure 2: LangGraph Agent Workflow**

### 3.4 Design Justifications

Several key design choices shaped the architecture.

**Structure-Aware Chunking:** We use structure-aware chunking instead of naive token-based splitting because regulatory documents have inherent hierarchical structure. A rule provision often spans multiple paragraphs. Splitting it arbitrarily would break the logical flow. By preserving rule numbers and section titles in chunk metadata, we enable more precise retrieval and citation generation. Users can also trace answers back to the original document structure more easily [12].

**Hybrid Retrieval:** We combine BM25 and dense embeddings instead of using only dense retrieval. As discussed in Section 2.1, keyword-based methods provide high precision for exact term matches, which is important in legal contexts where specific terminology matters. Dense retrieval adds recall by capturing semantic similarity. The hybrid approach balances these strengths.

**LangGraph for Workflow Orchestration:** We chose LangGraph over a hardcoded pipeline because it supports conditional branching. This allows the system to decide at runtime whether a second retrieval pass is needed. A hardcoded pipeline would either always perform two retrievals (wasting time on simple queries) or never perform a second retrieval (missing evidence for complex queries). LangGraph gives us the flexibility to adapt based on intermediate results.

**Lightweight Agentic Approach:** For Phase 1, we kept the agentic design simple. The planner uses heuristic classification rather than full LLM-driven reasoning. This reduces latency and cost while still providing the core benefit of conditional retrieval. In Phase 2, we plan to upgrade the planner to use LLM-based reasoning for better query understanding.

---

## 4. Methodology and Algorithms

Following the system architecture presented in Section 3, this section details the specific algorithms and methodologies used in each module.

### 4.1 Knowledge Base Construction Pipeline

The ingestion pipeline focuses on maintaining structural fidelity when converting regulatory documents. The process follows four steps:

1. **Format Handling:** The DocumentLoader uses regex-based pattern matching to differentiate between rule headers, section titles, and body text. For PDF inputs, we use pypdf for text extraction, though complex tables and multi-column layouts are not fully supported in Phase 1.

2. **Text Normalization:** The DocumentCleaner applies standard preprocessing: encoding conversion to UTF-8, removal of non-breaking spaces, and normalization of line breaks. This step also removes page numbers and footer text that appear in PDF extracts.

3. **Structure-Aware Chunking:** Unlike standard splitters, our Chunker implements a hierarchical parsing strategy that respects document structure. Details are provided in Section 4.2.

4. **Metadata Mapping:** Metadata is extracted during the parsing phase and mapped to a JSON schema before storage. Chunks are stored in data/chunks/ as JSON files, which allows efficient downstream loading for indexing.

### 4.2 Structure-Aware Chunking Algorithm

The chunking algorithm avoids naive token limits by prioritizing logical document boundaries.

```python
def structure_aware_chunk(document):
    hierarchy = parse_hierarchy(document)  # Uses regex for Chapter/Rule patterns
    chunks = []
    for section in hierarchy:
        # Avoid splitting if section is within size constraints
        if len(section.text) <= MAX_CHUNK_LENGTH:
            chunks.append(create_chunk(section))
        else:
            # Recursive split at natural paragraph breaks
            chunks.extend(recursive_split(section, MAX_CHUNK_LENGTH))
    return enrich_metadata(chunks)
```

Splitting text by token count often fails in legal documents. It might cut a rule in half or separate it from its context. We use a structure-aware approach instead:

1. **Parse Hierarchy:** The system looks for patterns like "Chapter 14A", section headings, and rule numbers (e.g., "14A.35").

2. **Context Preservation:** Each chunk is kept as a self-contained unit with its rule number and section context.

3. **Split Logic:** If a rule is too long (over 512 tokens), the system splits it at natural breaks like paragraphs or lists, rather than at fixed character counts.

4. **Metadata:** Metadata is extracted during the parsing phase and mapped to a JSON schema before storage. Chunks are stored in data/chunks/ as JSON files, which allows efficient downstream loading for indexing.

### 4.3 Hybrid Retrieval Strategy

We combine lexical and semantic search to maximize retrieval robustness [13, 14].

1. **BM25:** Used for exact keyword matching, prioritizing rule-specific terminology.

2. **Dense Retrieval:** We use BGE-M3 embeddings via Ollama [16] to capture semantic intent.

3. **Score Fusion:** Scores are normalized to the [0, 1] range using Min-Max scaling before weighted fusion:
   ```
   final_score = w1 * bm25_score + w2 * dense_score
   ```

4. **Deduplication:** Finally, we filter by chunk_id to remove duplicate results returned by both indices.

### 4.4 Agentic Workflow: Planning, Retrieval and Reasoning

The system uses LangGraph to manage the agent workflow. The process runs in a loop:

1. **Planner:** The PlannerNode decides if the query is direct or multi_hop. If multi_hop, it breaks the question into sub-queries.

2. **Retriever:** The RetrieverNode searches both BM25 and FAISS indexes and keeps the results in the state.

3. **Router:** The RouterNode decides if a second search is needed. It checks if the current chunks answer all sub-queries (with a relevance score over 0.3).

4. **Second Retrieval:** If needed, the SecondRetrievalNode reformulates the query to fill in the missing information.

5. **Reasoning:** The ReasoningNode uses DeepSeek Reasoner to generate an answer from all retrieved evidence.

6. **Citation:** The CitationFormatterNode adds rule numbers and source references to the answer.

### 4.5 Current Limitations and Planned Enhancements

As an MVP, the system has limitations that will be addressed in Phase 2:

1. **Heuristic Planner:** Currently rule-based. We plan to shift to LLM-driven planning for better query understanding.

2. **Evidence Coverage:** Second retrieval is triggered by simple relevance thresholds. This will be upgraded to an evidence-coverage checking model [9].

3. **Tool Integration:** While the interface is implemented, we have not yet integrated external tools such as financial calculators.

4. **Memory and Context:** The system is stateless. Adding conversational memory will be a priority.

5. **Formal Evaluation:** Rigorous evaluation using RAGAS is scheduled for the next phase.

---

## 5. Preliminary Performance Analysis or Experiments

### 5.1 Experimental Setup

This section reports early-stage feasibility testing. It is not a comprehensive benchmark evaluation. The goal is to check that the core pipeline works end-to-end and produces reasonable outputs.

**Table 2: Experimental Environment**

| Component | Specification |
|-----------|---------------|
| OS | Windows 11 |
| CPU | AMD Ryzen 7 |
| RAM | 16 GB |
| GPU | Not required |
| Python | 3.13.5 |
| Backend | FastAPI 0.135.1, Uvicorn 0.41.0 |
| Workflow | LangGraph 1.0.10, LangChain 1.2.10 |
| Lexical Index | rank-bm25 0.2.2 |
| Vector Index | FAISS 1.13.2 |
| Embeddings | BGE-M3 via Ollama |
| LLM Client | DeepSeek Reasoner API |
| Validation | Pydantic 2.11.7 |
| Testing | pytest 8.3.4 |
| Test Documents | HKEX Main Board Listing Rules excerpts |

The test document set consists of excerpts from the rulebook, not the full consolidated version. This is enough for validating the pipeline, but it does not represent the scale of a production deployment.

### 5.2 Functional Verification

We have 68 unit and integration tests across 8 test files. These tests cover the following modules:

**Table 3: Test Coverage Summary**

| Test File | Module | Tests | Status |
|-----------|--------|-------|--------|
| test_chunker.py | Structure-aware chunking | 12 | Pass |
| test_cleaner.py | Text cleaning | 6 | Pass |
| test_hybrid_retrieval.py | BM25 + Dense + Fusion | 14 | Pass |
| test_planner.py | Query classification | 8 | Pass |
| test_planner_refactor.py | LLM route planner + validators | 14 | Pass |
| test_chat_api.py | API endpoint | 4 | Pass |
| test_stage1_agentic_components.py | Agentic components | 6 | Pass |
| test_integration_v2.py | End-to-end workflow | 4 | Pass |

Key verifications include:
- Documents are ingested and chunks are generated with correct metadata fields
- BM25 and FAISS indexes build without errors
- The hybrid retriever returns ranked results with fused scores
- The API endpoint accepts queries and returns structured JSON responses
- Citations in the output can be traced back to specific chunk IDs and rule numbers

---

## 6. Milestones and Overall Schedule

### 6.1 Work Completed So Far

Phase 1 focused on building a functional backend prototype. Our work includes three main areas:

**Knowledge Base Construction:** We built a document ingestion pipeline that loads, cleans, and chunks HKEX regulatory documents. The pipeline preserves their hierarchical structure and builds two indexes: BM25 for lexical matching and FAISS with BGE-M3 embeddings for semantic retrieval.

**Agentic Retrieval & Reasoning:** We implemented a LangGraph-based workflow with a heuristic planner, hybrid retriever, conditional router, and reasoning agent using DeepSeek Reasoner. The system classifies queries as direct or multi_hop. It can trigger a second retrieval when needed and generates answers with citations. We also developed Stage 1 enhancements, including an LLM-driven route planner, task decomposer, and validation components.

**System Integration & Testing:** We built a FastAPI backend with /health and /chat endpoints. We also wrote 68 unit and integration tests that cover ingestion, retrieval, agentic nodes, and API functionality. Project documentation includes design specifications, usage guides, and this interim report.

### 6.2 Project Schedule and Milestones

We are now moving from the Phase 1 prototype to Phase 2. In Phase 2, we will focus on reasoning quality, specialized tools, and formal evaluation.

**Table 4: Project schedule**

| Phase | Timeline | Deliverables |
|-------|----------|--------------|
| Phase 1 | February – March 2025 | Backend prototype with core workflow. We have completed this phase. |
| Phase 2 | April – May 2025 | LLM-driven planner and evidence coverage check. We are currently in this phase. |
| Phase 3 | June 2025 | Tool integration, benchmark dataset, and formal evaluation. |
| Final Report | July 2025 | Comprehensive evaluation, error analysis, and system demonstration. |

---

## 7. Work to be Completed for the Next Report

### 7.1 Technical Improvements

Following the schedule outlined in Table 4, the next phase addresses the limitations identified in Section 4.5 and Section 5.2. Here we outline the main technical improvements planned for Phase 2.

**LLM-Driven Planner:** The current planner uses heuristic rules to classify queries. This works for simple cases but struggles with ambiguous or complex questions. We will replace the heuristic planner with an LLM-based planner that can better understand query intent. The LLM will analyze the question and decide whether it requires single-step or multi-step retrieval.

**Evidence Coverage Check:** The current system triggers a second retrieval based on simple relevance thresholds. This is not always accurate. We will implement an evidence coverage checker that uses an LLM to evaluate whether the retrieved chunks provide enough information to answer all parts of the query. If not, the system will reformulate the query and retrieve again.

**Tool Integration:** The tool interface will be implemented for specialized compliance tasks. We will start with a Size Test Calculator that can compute percentage ratios for transaction classification. This will allow the system to handle queries like "Is this transaction a major transaction?" by performing the necessary calculations.

**Retrieval Improvements:** The score fusion strategy will be upgraded from weighted linear combination to Reciprocal Rank Fusion (RRF). RRF is more robust to score scale differences between BM25 and dense retrieval.

### 7.2 Evaluation and Reporting Work

Formal evaluation is essential for validating the system's performance in a regulatory compliance context.

**Benchmark Dataset:** A benchmark dataset with 20-30 annotated compliance questions will be constructed. It will cover direct lookups, multi-hop reasoning, and edge cases where the system should flag uncertainty.

**Evaluation Metrics:** Metrics will be implemented for retrieval recall (whether the correct chunks are retrieved), citation quality (whether citations are accurate and traceable), and answer correctness (whether the generated answer is factually correct based on the rules).

**Baseline Comparison:** The agentic RAG system will be compared against baseline approaches, including standard single-pass RAG and keyword-based search. This will show the value of the agentic workflow.

**System Demonstration:** A recorded demonstration will be prepared showing the system handling representative compliance queries. This will include cases where it correctly triggers second retrieval, uses tools, and flags uncertainty.

**Final Report:** The final report will include comprehensive results, error analysis using RAGAS [9], and a discussion of the system's capabilities and limitations as a research prototype.

---

## 8. References

[1] Hong Kong Exchanges and Clearing Limited, "Market highlights," 2025. [Online]. Available: https://www.hkex.com.hk/Market-Data/Statistics

[2] Hong Kong Exchanges and Clearing Limited, "Main Board Listing Rules," consolidated version. [Online]. Available: https://en-rules.hkex.com.hk/rulebook/main-board-listing-rules

[3] Hong Kong Exchanges and Clearing Limited, "Rules & resources — Guidance." [Online]. Available: https://www.hkex.com.hk/Listing/Rules-and-Resources/Guidance

[4] H. Zhong et al., "Legal retrieval and question answering: A survey," arXiv preprint arXiv:2210.13314, 2022.

[5] L. Wang et al., "A survey on large language model based autonomous agents," arXiv preprint arXiv:2308.11432, 2023.

[6] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," Found. Trends Inf. Retr., vol. 3, no. 4, pp. 333–389, 2009.

[7] Y. Shao et al., "Enhancing retrieval-augmented large language models with iterative retrieval-generation synergy," in Findings of the 2023 Conference on Empirical Methods in Natural Language Processing, 2023.

[8] D. M. Katz, "Legal tech, smart contracts and blockchain," in Perspectives on Law and Innovation. Cheltenham, UK: Edward Elgar Publishing, 2018.

[9] S. Es, J. James, L. Espinosa-Anke, and S. Schockaert, "RAGAS: Automated evaluation of retrieval augmented generation," arXiv preprint arXiv:2309.15217, 2023.

[10] H. Zhong et al., "JEC-QA: A legal-domain question answering dataset," in Proc. AAAI Conf. Artif. Intell., vol. 34, no. 5, pp. 9701–9708, 2020.

[11] R. Susskind, Tomorrow's Lawyers: An Introduction to Your Future. Oxford, UK: Oxford Univ. Press, 2017.

[12] C. D. Manning, P. Raghavan, and H. Schütze, Introduction to Information Retrieval. Cambridge, UK: Cambridge Univ. Press, 2008.

[13] V. Karpukhin et al., "Dense passage retrieval for open-domain question answering," in Proc. 2020 Conf. Empirical Methods Nat. Lang. Process., 2020, pp. 6769–6781.

[14] J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, "BERT: Pre-training of deep bidirectional transformers for language understanding," in Proc. 2019 Conf. North Amer. Chapter Assoc. Comput. Linguistics: Hum. Lang. Technol., 2019, pp. 4171–4186.

[15] C. Xiao et al., "C-Pack: Packaged resources to advance general Chinese embedding," arXiv preprint arXiv:2309.07597, 2023.

[16] P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in Adv. Neural Inf. Process. Syst., vol. 33, 2020, pp. 9459–9474.

[17] Y. Gao et al., "Retrieval-augmented generation for large language models: A survey," arXiv preprint arXiv:2312.10997, 2023.

[18] LangChain, "LangGraph: A framework for building stateful agent workflows," 2024. [Online]. Available: https://langchain-ai.github.io/langgraph/