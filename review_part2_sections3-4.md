# 中期报告文字风格修改建议 - Section 3-4 (Humanized)

## Section 3: System Modeling and Structure

### 3.1 Problem Scope and System Boundary

**\[真实原文]**

> This project focuses on a specific subset of the HKEX Listing Rules: Notifiable Transactions (Chapter 14), Connected Transactions (Chapter 14A), Size Tests (Rule 14.07 and related provisions), and associated disclosure obligations. We chose these areas because they come up frequently in compliance questions and involve cross-referencing between multiple rule provisions.

**\[去AI味修改建议]**

- **AI味特征：** "come up frequently" 略显口语化但可接受；"involve cross-referencing" 稍显正式。
- **研究生风格（去AI化）：**

> This project focuses on a specific subset of the HKEX Listing Rules: Notifiable Transactions (Chapter 14), Connected Transactions (Chapter 14A), Size Tests (Rule 14.07 and related provisions), and associated disclosure obligations. We chose these areas because they appear frequently in compliance questions. They also require cross-referencing between multiple rule provisions.

***

### 3.2 Overall Architecture

**\[真实原文]**

> The system follows a pipeline with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation. Figure 1 shows the overall architecture.

**\[去AI味修改建议]**

- **AI味特征：** 过于简洁完美。
- **研究生风格（去AI化）：**

> The system follows a pipeline with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation. The overall architecture is shown in Figure 1.

***

**\[真实原文]**

> The first four modules run offline during document preparation. Document Ingestion supports plain text, Markdown, and PDF, though PDF support is basic in Phase 1. Cleaning normalizes text by removing excessive whitespace, fixing encoding issues, and standardizing line breaks. Chunking preserves document structure: instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers, then creates chunks that keep these elements intact. Indexing builds two retrieval indexes: BM25 for keyword search and FAISS for semantic search using BGE-M3 embeddings.

**\[去AI味修改建议]**

- **AI味特征：** "preserves document structure: instead of" (AI常用冒号解释句式)；句子过长。
- **研究生风格（去AI化）：**

> The first four modules run offline during document preparation. Document Ingestion supports plain text, Markdown, and PDF. PDF support is still basic in Phase 1. Cleaning normalizes text by removing excessive whitespace, fixing encoding issues, and standardizing line breaks.
>
> Chunking preserves document structure. Instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers. Then it creates chunks that keep these elements intact. Indexing builds two retrieval indexes: BM25 for keyword search and FAISS for semantic search using BGE-M3 embeddings.

***

**\[真实原文]**

> The last two modules run online during query time. Query Processing routes the user's question through the LangGraph workflow described in Section 3.3. Response Generation synthesizes the answer using DeepSeek Reasoner and formats citations with traceable rule numbers.

**\[去AI味修改建议]**

- **AI味特征：** "synthesizes the answer" (过于正式)；"formats citations with traceable rule numbers" (过于完美)。
- **研究生风格（去AI化）：**

> The last two modules run online during query time. Query Processing routes the user's question through the LangGraph workflow described in Section 3.3. Response Generation generates the answer using DeepSeek Reasoner and adds citations with rule numbers.

***

### 3.3 LangGraph Workflow Structure

**\[真实原文]**

> Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph allows conditional branching based on intermediate results. Figure 2 shows the workflow.

**\[去AI味修改建议]**

- **AI味特征：** 过于简洁。
- **研究生风格（去AI化）：**

> Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph can do conditional branching based on intermediate results. The workflow is shown in Figure 2.

***

**\[真实原文]**

> The workflow starts at the Planner Node, which classifies the query as direct (simple rule lookup) or multi\_hop (requires combining multiple rules). For multi-hop queries, the Planner also breaks the question into sub-queries. Classification uses heuristic rules based on keyword patterns, checking for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

**\[去AI味修改建议]**

- **AI味特征：** 句子过长；"checking for conjunctions like...and phrases that indicate" (过于完美的并列)。
- **研究生风格（去AI化）：**

> The workflow starts at the Planner Node. It classifies the query as direct (simple rule lookup) or multi\_hop (requires combining multiple rules). For multi-hop queries, the Planner also breaks the question into sub-queries. Classification uses heuristic rules based on keyword patterns. It checks for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

***

**\[真实原文]**

> The Retriever Node performs hybrid retrieval by querying both BM25 and FAISS indexes. It retrieves top-k chunks from each, normalizes scores to a \[0, 1] range. Retrieved chunks go into the workflow state.

**\[去AI味修改建议]**

- **AI味特征：** "normalizes scores to a \[0, 1] range" (过于技术化)；最后一句过于简短。
- **研究生风格（去AI化）：**

> The Retriever Node performs hybrid retrieval by querying both BM25 and FAISS indexes. It retrieves top-k chunks from each and normalizes scores to a \[0, 1] range. Then retrieved chunks are stored in the workflow state.

***

**\[真实原文]**

> The Conditional Router checks whether the retrieved evidence covers all sub-queries. Specifically, for each sub-query generated by the Planner, the router checks whether at least one retrieved chunk has a relevance score above a minimum threshold (0.3 in Phase 1). If any sub-query lacks supporting evidence, the router sets needs\_second\_retrieval = True and sends the workflow to the Second Retrieval Node. For direct queries, the router always proceeds to reasoning.

**\[去AI味修改建议]**

- **AI味特征：** "Specifically" (AI高频词)；句子过长且过于完美。
- **研究生风格（去AI化）：**

> The Conditional Router checks whether the retrieved evidence covers all sub-queries. For each sub-query generated by the Planner, the router checks if at least one retrieved chunk has a relevance score above a minimum threshold (0.3 in Phase 1). If any sub-query lacks supporting evidence, the router sets needs\_second\_retrieval = True and sends the workflow to the Second Retrieval Node. For direct queries, the router always proceeds to reasoning.

***

**\[真实原文]**

> The Second Retrieval Node performs another retrieval pass using the uncovered sub-queries as new search terms. Newly retrieved chunks are appended to the state, deduplicated by chunk\_id.

**\[去AI味修改建议]**

- **AI味特征：** "deduplicated by chunk\_id" (过于技术化)。
- **研究生风格（去AI化）：**

> The Second Retrieval Node performs another retrieval pass using the uncovered sub-queries as new search terms. Newly retrieved chunks are added to the state and deduplicated by chunk\_id.

***

**\[真实原文]**

> The Reasoning Node uses DeepSeek Reasoner to synthesize an answer based on all retrieved chunks. The prompt instructs the LLM to ground every claim in the retrieved evidence and include an uncertainty note if evidence is incomplete.

**\[去AI味修改建议]**

- **AI味特征：** "synthesize an answer" (过于正式)；"ground every claim in" (学术套话)。
- **研究生风格（去AI化）：**

> The Reasoning Node uses DeepSeek Reasoner to generate an answer based on all retrieved chunks. The prompt tells the LLM to base every claim on the retrieved evidence and include an uncertainty note if evidence is incomplete.

***

**\[真实原文]**

> The Citation Formatter Node post-processes the answer to ensure citations are properly formatted with rule numbers, chapter references, and source document identifiers. The final structured response is returned to the user.

**\[去AI味修改建议]**

- **AI味特征：** "post-processes...to ensure" (AI常用句式)；"properly formatted" (过于正式)。
- **研究生风格（去AI化）：**

> The Citation Formatter Node processes the answer to make sure citations are correctly formatted with rule numbers, chapter references, and source document identifiers. The final structured response is then returned to the user.

***

### 3.4 Design Justifications

**\[真实原文]**

> Several key design choices shaped the architecture.

**\[去AI味修改建议]**

- **AI味特征：** 过于简洁。
- **研究生风格（去AI化）：**

> We made several key design choices when building the architecture.

***

**\[真实原文]**

> Structure-Aware Chunking: We use structure-aware chunking instead of naive token-based splitting because regulatory documents have inherent hierarchical structure. A rule provision often spans multiple paragraphs. Splitting it arbitrarily would break the logical flow. By preserving rule numbers and section titles in chunk metadata, we enable more precise retrieval and citation generation. Users can also trace answers back to the original document structure more easily \[12].

**\[去AI味修改建议]**

- **AI味特征：** "instead of naive token-based splitting because" (AI对比句式)；"By preserving...we enable" (AI因果句式)。
- **研究生风格（去AI化）：**

> Structure-Aware Chunking: We use structure-aware chunking rather than simple token-based splitting. Regulatory documents have inherent hierarchical structure. A rule provision often spans multiple paragraphs. If we split it arbitrarily, we would break the logical flow. We preserve rule numbers and section titles in chunk metadata. This enables more precise retrieval and citation generation. Users can also trace answers back to the original document structure more easily \[12].

***

**\[真实原文]**

> Hybrid Retrieval: We combine BM25 and dense embeddings instead of using only dense retrieval. As discussed in Section 2.1, BM25 is reliable for exact keyword matches, while dense embeddings handle semantic similarity. Combining both ensures that documents with exact keyword matches are not overlooked \[13]. The hybrid approach also balances precision and recall, capturing both lexically similar and semantically related chunks \[14].

**\[去AI味修改建议]**

- **AI味特征：** "instead of using only" (AI对比句式)；"ensures that...are not overlooked" (过于完美)。
- **研究生风格（去AI化）：**

> Hybrid Retrieval: We combine BM25 and dense embeddings rather than using only dense retrieval. As discussed in Section 2.1, BM25 is reliable for exact keyword matches. Dense embeddings handle semantic similarity. Combining both makes sure that documents with exact keyword matches are not missed \[13]. The hybrid approach also balances precision and recall. It captures both lexically similar and semantically related chunks \[14].

***

**\[真实原文]**

> LangGraph for Workflow Orchestration: We chose LangGraph over a hardcoded pipeline because it supports conditional branching and stateful execution \[18]. This matters for the conditional second retrieval step. If the router determines that evidence is insufficient, the workflow can branch to a second retrieval node. A hardcoded pipeline would require manual if-else logic scattered across multiple functions, making the code harder to maintain and extend.

**\[去AI味修改建议]**

- **AI味特征：** "We chose X over Y because" (AI对比句式)；"This matters for" (AI常用过渡)。
- **研究生风格（去AI化）：**

> LangGraph for Workflow Orchestration: We chose LangGraph instead of a hardcoded pipeline. LangGraph supports conditional branching and stateful execution \[18]. This is important for the conditional second retrieval step. If the router determines that evidence is insufficient, the workflow can branch to a second retrieval node. A hardcoded pipeline would need manual if-else logic scattered across multiple functions. This would make the code harder to maintain and extend.

***

**\[真实原文]**

> Lightweight Agentic Approach: For Phase 1, we kept the agentic design simple. The planner uses heuristic classification instead of full LLM-based reasoning. This reduces latency and cost while still enabling multi-step retrieval. More sophisticated planning will be added in Phase 2 once the core workflow is validated.

**\[去AI味修改建议]**

- **AI味特征：** "instead of full LLM-based reasoning" (AI对比句式)；"while still enabling" (AI常用while从句)。
- **研究生风格（去AI化）：**

> Lightweight Agentic Approach: For Phase 1, we kept the agentic design simple. The planner uses heuristic classification rather than full LLM-based reasoning. This reduces latency and cost but still enables multi-step retrieval. We will add more sophisticated planning in Phase 2 once the core workflow is validated.

***

## Section 4: Methodology and Algorithms

### 4.1 Knowledge Base Construction Pipeline

**\[真实原文]**

> The ingestion pipeline focuses on maintaining structural fidelity when converting regulatory documents. The process follows four stages:

**\[去AI味修改建议]**

- **AI味特征：** "focuses on maintaining structural fidelity" (过于正式)。
- **研究生风格（去AI化）：**

> The ingestion pipeline tries to maintain the document structure when converting regulatory documents. The process has four stages:

***

**\[真实原文]**

> Format Handling: The DocumentLoader employs regex-based pattern matching to differentiate between rule headers, section titles, and body text. This ensures that structural markers are preserved during ingestion.

**\[去AI味修改建议]**

- **AI味特征：** "employs regex-based pattern matching to differentiate" (过于正式)；"This ensures that" (AI常用句式)。
- **研究生风格（去AI化）：**

> Format Handling: The DocumentLoader uses regex-based pattern matching to identify rule headers, section titles, and body text. This helps preserve structural markers during ingestion.

***

**\[真实原文]**

> Text Normalization: The DocumentCleaner applies standard preprocessing: encoding conversion to UTF-8, removal of non-breaking spaces, and normalization of line breaks. This step ensures consistent text representation across different source formats.

**\[去AI味修改建议]**

- **AI味特征：** "applies standard preprocessing:" (AI常用冒号解释)；"This step ensures" (AI常用句式)。
- **研究生风格（去AI化）：**

> Text Normalization: The DocumentCleaner does standard preprocessing. It converts encoding to UTF-8, removes non-breaking spaces, and normalizes line breaks. This step makes sure the text representation is consistent across different source formats.

***

**\[真实原文]**

> Structure-Aware Chunking: Unlike standard splitters, our Chunker implements a hierarchical parsing strategy that respects the rulebook's structure \[12]. Chunks are created at natural boundaries (e.g., rule provisions, subsections) rather than at fixed token counts.

**\[去AI味修改建议]**

- **AI味特征：** "Unlike standard splitters" (AI对比句式)；"implements a hierarchical parsing strategy that respects" (过于正式)。
- **研究生风格（去AI化）：**

> Structure-Aware Chunking: Our Chunker is different from standard splitters. It uses a hierarchical parsing strategy that respects the rulebook's structure \[12]. Chunks are created at natural boundaries (e.g., rule provisions, subsections) instead of at fixed token counts.

***

**\[真实原文]**

> Metadata Mapping: Metadata is extracted during the parsing phase and mapped to a JSON schema before storage. Chunks are persisted in data/chunks/ as JSON files, enabling efficient downstream loading for indexing.

**\[去AI味修改建议]**

- **AI味特征：** "is extracted...and mapped to" (被动语态过多)；"enabling efficient downstream loading" (过于技术化)。
- **研究生风格（去AI化）：**

> Metadata Mapping: We extract metadata during the parsing phase and map it to a JSON schema before storage. Chunks are saved in data/chunks/ as JSON files. This makes it easier to load them later for indexing.

***

### 4.2 Structure-Aware Chunking Algorithm

**\[真实原文]**

> The chunking algorithm avoids naive token limits by prioritizing logical document boundaries.

**\[去AI味修改建议]**

- **AI味特征：** "avoids naive token limits by prioritizing" (AI因果句式)。
- **研究生风格（去AI化）：**

> The chunking algorithm does not use simple token limits. Instead, it prioritizes logical document boundaries.

***

**\[真实原文]**

> Splitting text by token count often fails in legal documents. It might cut a rule in half or separate it from its context. We use a structure-aware approach instead:

**\[去AI味修改建议]**

- **AI味特征：** "We use a structure-aware approach instead:" (AI常用冒号解释)。
- **研究生风格（去AI化）：**

> Splitting text by token count often fails in legal documents. It might cut a rule in half or separate it from its context. So we use a structure-aware approach:

***

**\[真实原文]**

> 1. Parse Hierarchy: The system looks for patterns like "Chapter 14A", section headings, and rule numbers (e.g., "14A.35").
> 2. Context Preservation: Each chunk is kept as a self-contained unit with its rule number and section context.
> 3. Split Logic: If a rule is too long (over 512 tokens), the system splits it at natural breaks like paragraphs or lists, rather than at fixed character counts.
> 4. Metadata: Metadata is extracted during the parsing phase and mapped to a JSON schema before storage. Chunks are persisted in data/chunks/ as JSON files, enabling efficient downstream loading for indexing.

**\[去AI味修改建议]**

- **AI味特征：** "rather than at fixed character counts" (AI对比句式)；"enabling efficient downstream loading" (过于技术化)。
- **研究生风格（去AI化）：**

> 1. Parse Hierarchy: The system looks for patterns like "Chapter 14A", section headings, and rule numbers (e.g., "14A.35").
> 2. Context Preservation: Each chunk is kept as a self-contained unit with its rule number and section context.
> 3. Split Logic: If a rule is too long (over 512 tokens), the system splits it at natural breaks like paragraphs or lists instead of at fixed character counts.
> 4. Metadata: We extract metadata during the parsing phase and map it to a JSON schema before storage. Chunks are saved in data/chunks/ as JSON files. This makes it easier to load them later for indexing.

***

### 4.3 Hybrid Retrieval Strategy

**\[真实原文]**

> We combine lexical and semantic search to maximize retrieval robustness \[13, 14].

**\[去AI味修改建议]**

- **AI味特征：** "to maximize retrieval robustness" (过于正式)。
- **研究生风格（去AI化）：**

> We combine lexical and semantic search to make retrieval more robust \[13, 14].

***

**\[真实原文]**

> 1. BM25: Used for exact keyword matching, prioritizing rule-specific terminology.
> 2. Dense Retrieval: We use BGE-M3 embeddings via Ollama \[16] to capture semantic intent.
> 3. Score Fusion: Scores are normalized to the \[0, 1] range using Min-Max scaling before weighted fusion:
> 4. Deduplication: Finally, we filter by chunk\_id to remove duplicate results returned by both indices.

**\[去AI味修改建议]**

- **AI味特征：** "prioritizing rule-specific terminology" (过于正式)；"to capture semantic intent" (学术套话)。
- **研究生风格（去AI化）：**

> 1. BM25: Used for exact keyword matching. It prioritizes rule-specific terminology.
> 2. Dense Retrieval: We use BGE-M3 embeddings via Ollama \[16] to capture semantic meaning.
> 3. Score Fusion: Scores are normalized to the \[0, 1] range using Min-Max scaling before weighted fusion:
> 4. Deduplication: Finally, we filter by chunk\_id to remove duplicate results from both indices.

***

### 4.4 Agentic Workflow: Planning, Retrieval and Reasoning

**\[真实原文]**

> The system uses LangGraph to manage the agent workflow. The process runs in a loop:

**\[去AI味修改建议]**

- **AI味特征：** 无明显问题，保持原样。

***

**\[真实原文]**

> 1. Planner: The PlannerNode decides if the query is direct or multi\_hop. If multi\_hop, it breaks the question into sub-queries.
> 2. Retriever: The RetrieverNode searches both BM25 and FAISS indexes and keeps the results in the state.
> 3. Router: The RouterNode decides if a second search is needed. It checks if the current chunks answer all sub-queries (with a relevance score over 0.3).
> 4. Second Retrieval: If needed, the SecondRetrievalNode reformulates the query to fill in the missing information.
> 5. Reasoning: The ReasoningNode uses DeepSeek Reasoner to synthesize an answer from all retrieved evidence.
> 6. Citation: The CitationFormatterNode adds rule numbers and source references to the answer.

**\[去AI味修改建议]**

- **AI味特征：** "synthesize an answer from" (过于正式)；"to fill in the missing information" (AI常用to不定式)。
- **研究生风格（去AI化）：**

> 1. Planner: The PlannerNode decides if the query is direct or multi\_hop. If multi\_hop, it breaks the question into sub-queries.
> 2. Retriever: The RetrieverNode searches both BM25 and FAISS indexes and stores the results in the state.
> 3. Router: The RouterNode decides if a second search is needed. It checks if the current chunks answer all sub-queries (with a relevance score over 0.3).
> 4. Second Retrieval: If needed, the SecondRetrievalNode reformulates the query and fills in the missing information.
> 5. Reasoning: The ReasoningNode uses DeepSeek Reasoner to generate an answer from all retrieved evidence.
> 6. Citation: The CitationFormatterNode adds rule numbers and source references to the answer.

***

### 4.5 Current Limitations and Planned Enhancements

**\[真实原文]**

> As an MVP, the system has limitations that will be addressed in Phase 2:

**\[去AI味修改建议]**

- **AI味特征：** "that will be addressed in" (被动语态)。
- **研究生风格（去AI化）：**

> As an MVP, the system has some limitations. We will address these in Phase 2:

***

**\[真实原文]**

> 1. Heuristic Planner: Currently rule-based; we intend to shift to LLM-driven planning for better query understanding.
> 2. Evidence Coverage: Second retrieval is triggered by simple relevance thresholds; this will be upgraded to an evidence-coverage checking model \[9].
> 3. Tool Integration: While the interface is implemented, we have not yet integrated external tools such as financial calculators.
> 4. Memory and Context: The system is stateless. Adding conversational memory will be a priority.
> 5. Formal Evaluation: Rigorous evaluation using RAGAS is scheduled for the next phase.

**\[去AI味修改建议]**

- **AI味特征：** "we intend to shift to" (过于正式)；"While the interface is implemented" (AI常用while从句)。
- **研究生风格（去AI化）：**

> 1. Heuristic Planner: Currently rule-based. We plan to shift to LLM-driven planning for better query understanding.
> 2. Evidence Coverage: Second retrieval is triggered by simple relevance thresholds. We will upgrade this to an evidence-coverage checking model \[9].
> 3. Tool Integration: The interface is implemented, but we have not yet integrated external tools like financial calculators.
> 4. Memory and Context: The system is stateless. We will add conversational memory as a priority.
> 5. Formal Evaluation: We will do rigorous evaluation using RAGAS in the next phase.

***

## 总结：Section 3-4 主要AI味特征

### 高频AI句式（已修改）

1. "X instead of Y because..." → 拆成多句
2. "By doing X, we enable Y" → "We do X. This enables Y"
3. "This ensures that..." → "This makes sure..."
4. "employs/implements/utilizes" → "uses"
5. "synthesize" → "generate"
6. "While X, Y" → 拆成两句

### 修改后的效果

- 句子更短，更直接
- 减少被动语态
- 使用更简单的动词
- 保留技术准确性但降低"书卷气"

