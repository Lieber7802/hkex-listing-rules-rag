# 3. System Modeling and Structure

Building on the approaches discussed in Section 2, this section defines the scope, architecture, and workflow of our system.

## 3.1 Problem Scope and System Boundary

This project focuses on a specific subset of the HKEX Listing Rules: Notifiable Transactions (Chapter 14), Connected Transactions (Chapter 14A), Size Tests (Rule 14.07 and related provisions), and associated disclosure obligations. We chose these areas because they come up frequently in compliance questions and involve cross-referencing between multiple rule provisions.

Table 1 summarizes the system's input and output boundaries.

**Table 1: System Input/Output Specification**

| | Description | Format |
|---|---|---|
| Input | Natural language compliance question | JSON: `{"query": "..."}` |
| Output - Answer | Natural language response synthesizing relevant rules | `string` |
| Output - Citations | Rule numbers, chapter references, source identifiers | `List[Citation]` |
| Output - Evidence | Retrieved chunks used as supporting evidence | `List[Chunk]` |
| Output - Uncertainty | Note indicating incomplete or conflicting evidence | `string` or `null` |

For example, a user might ask: "What are the disclosure requirements for a connected transaction?" The system returns a structured JSON response containing all four output components.

As noted in Section 1.2, Phase 1 excludes frontend, specialized tools, benchmark datasets, formal evaluation, and production deployment. These exclusions let us focus on the core workflow: query planning, hybrid retrieval, and generating answers with traceable citations.

## 3.2 Overall Architecture

The system follows a pipeline with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation. Figure 1 shows the overall architecture. Table 2 summarizes each module.

[Figure 1: System Architecture Overview]

**Table 2: System Module Summary**

| Module | Responsibility | Input | Output |
|---|---|---|---|
| Document Ingestion | Load raw documents from `data/raw/` | PDF, TXT, MD files | Raw text with source metadata |
| Cleaning | Normalize text, fix encoding | Raw text | Cleaned text |
| Chunking | Structure-aware splitting by rule/section | Cleaned text | Chunks with metadata (`rule_number`, `chapter`, `section_title`, `chunk_order`) |
| Indexing | Build dual retrieval indexes | Chunks | BM25 index + FAISS vector index (BGE-M3 via Ollama) |
| Query Processing | Plan, retrieve, route (see Section 3.3) | User query (JSON) | Retrieved evidence chunks |
| Response Generation | Synthesize answer, format citations | Evidence chunks | Structured response (answer + citations) |

The first four modules run offline during document preparation. Document Ingestion supports plain text, Markdown, and PDF, though PDF support is basic in Phase 1. Cleaning normalizes text by removing excessive whitespace, fixing encoding issues, and standardizing line breaks. Chunking preserves document structure: instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers, then creates chunks that keep these elements intact. Indexing builds two retrieval indexes: BM25 for keyword search and FAISS for semantic search using BGE-M3 embeddings.

The last two modules run online during query time. Query Processing routes the user's question through the LangGraph workflow described in Section 3.3. Response Generation synthesizes the answer using DeepSeek Reasoner and formats citations with traceable rule numbers.

Key configuration parameters for Phase 1 are listed in Table 3.

**Table 3: Key Configuration Parameters**

| Parameter | Value | Description |
|---|---|---|
| `k_bm25` | 10 | Top-k results from BM25 retrieval |
| `k_dense` | 10 | Top-k results from dense retrieval |
| `k_final` | 8 | Final merged results after deduplication |
| `bm25_weight` | 0.4 | Weight for BM25 scores in fusion |
| `dense_weight` | 0.6 | Weight for dense scores in fusion |
| `max_chunk_length` | 512 tokens | Maximum chunk size before secondary splitting |
| `embedding_model` | BGE-M3 | Dense embedding model via Ollama |
| `llm_model` | DeepSeek Reasoner | LLM for reasoning and answer generation |

## 3.3 LangGraph Workflow Structure

Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph allows conditional branching based on intermediate results. Figure 2 shows the workflow.

[Figure 2: LangGraph Agent Workflow]

The workflow starts at the **Planner Node**, which classifies the query as `direct` (simple rule lookup) or `multi_hop` (requires combining multiple rules). For multi-hop queries, the Planner also breaks the question into sub-queries. Classification uses heuristic rules based on keyword patterns, checking for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

The **Retriever Node** performs hybrid retrieval by querying both BM25 and FAISS indexes. It retrieves top-k chunks from each, normalizes scores to a [0, 1] range, and merges results by `chunk_id` using the weighted fusion described in Table 3. Retrieved chunks go into the workflow state.

The **Conditional Router** checks whether the retrieved evidence covers all sub-queries. Specifically, for each sub-query generated by the Planner, the router checks whether at least one retrieved chunk has a relevance score above a minimum threshold (0.3 in Phase 1). If any sub-query lacks supporting evidence, the router sets `needs_second_retrieval = True` and sends the workflow to the **Second Retrieval Node**. For `direct` queries, the router always proceeds to reasoning.

The **Second Retrieval Node** performs another retrieval pass using the uncovered sub-queries as new search terms. Newly retrieved chunks are appended to the state, deduplicated by `chunk_id`.

The **Reasoning Node** uses DeepSeek Reasoner to synthesize an answer based on all retrieved chunks. The prompt instructs the LLM to ground every claim in the retrieved evidence and include an uncertainty note if evidence is incomplete.

The **Citation Formatter Node** post-processes the answer to ensure citations are properly formatted with rule numbers, chapter references, and source document identifiers. The final structured response is returned to the user.

## 3.4 Design Justifications

Several key design choices shaped the architecture.

**Structure-Aware Chunking**: We use structure-aware chunking instead of naive token-based splitting because regulatory documents have inherent hierarchical structure. A rule provision often spans multiple paragraphs. Splitting it arbitrarily would break the logical flow. By preserving rule numbers and section titles in chunk metadata, we enable more precise retrieval and citation generation. Users can also trace answers back to the original document structure more easily [13].

**Hybrid Retrieval**: We combine BM25 and dense embeddings instead of using only dense retrieval. As discussed in Section 2.2, dense retrieval excels at semantic matching but can retrieve chunks that are semantically similar yet legally imprecise. BM25 ensures that chunks with exact keyword matches are not overlooked [14]. The hybrid approach balances recall with precision, which is particularly important for regulatory text where specific rule numbers and legal terms carry precise meaning [15].

**LangGraph for Workflow Orchestration**: We chose LangGraph over a hardcoded pipeline because it supports conditional branching and stateful execution [19]. This matters for the conditional second retrieval step, which only triggers when initial retrieval is insufficient. LangGraph also makes the workflow easier to extend. Adding new nodes (like a tool-calling node in Phase 2) requires minimal changes to the existing graph structure.

**Lightweight Agentic Approach**: For Phase 1, we kept the agentic design simple. The planner uses heuristic classification rather than full LLM-driven reasoning. The system does not yet support tool use or session memory. This reduces complexity and allows us to focus on validating the core workflow. A more sophisticated multi-agent system with specialized sub-agents for different rule categories would be more powerful, but would also introduce additional failure modes and debugging challenges that are not justified at the prototype stage.
