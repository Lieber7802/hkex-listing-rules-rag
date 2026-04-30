# 4. Methodology and Algorithms

Following the system architecture presented in Section 3, this section details the specific algorithms and methodologies used to implement each component.

## 4.1 Knowledge Base Construction Pipeline

The ingestion pipeline focuses on maintaining structural fidelity when converting regulatory documents. The process follows a deterministic sequence:

1. **Format Handling**: The `DocumentLoader` employs regex-based pattern matching to differentiate between rule headers, section titles, and body paragraphs. This allows the system to support `.txt`, `.md`, and basic `.pdf` (via text-layer extraction) formats.
2. **Text Normalization**: The `DocumentCleaner` applies standard preprocessing: encoding conversion to UTF-8, removal of non-breaking spaces, and normalization of line endings (`\n` vs `\r\n`).
3. **Structure-Aware Chunking**: Unlike standard splitters, our `Chunker` implements a hierarchical parsing strategy that respects the HKEX rulebook's structure [13].
4. **Metadata Mapping**: Metadata is extracted during the parsing phase and mapped to a JSON schema before storage. Chunks are persisted in `data/chunks/` as JSON files, enabling efficient downstream loading for indexing.

## 4.2 Structure-Aware Chunking Algorithm

The chunking algorithm avoids naive token limits by prioritizing logical document boundaries.

**Algorithm 1: Hierarchical Chunking**
```python
def structure_aware_chunk(document):
    hierarchy = parse_hierarchy(document) # Uses regex for Chapter/Rule patterns
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

By prioritizing these natural boundaries, we ensure that the retriever operates on contextually complete fragments. The extracted metadata fields, which are crucial for subsequent citation generation, are detailed in Table 4.

**Table 4: Chunk Metadata Fields**

| Field | Description |
|---|---|
| `chunk_id` | Unique ID (`doc_id:rule:order`) |
| `document_id` | Source identifier |
| `chapter` | Chapter title |
| `section_title` | Section title |
| `rule_number` | Rule identifier |
| `text` | Chunk content |
| `source_path` | File path |

## 4.3 Hybrid Retrieval Strategy

We combine lexical and semantic search to maximize retrieval robustness [14, 15].

1. **BM25**: Used for exact keyword matching, prioritizing rule-specific terminology.
2. **Dense Retrieval**: We use BGE-M3 embeddings via Ollama [16] to capture semantic intent.
3. **Score Fusion**: Scores are normalized to the [0, 1] range using Min-Max scaling before weighted fusion:
   $Score_{final} = w_1 \cdot Score_{bm25} + w_2 \cdot Score_{dense}$
   where $w_1=0.4$ and $w_2=0.6$. We note that Reciprocal Rank Fusion (RRF) is a more robust alternative that avoids score normalization sensitivity; replacing the current weighted fusion with RRF is planned for Phase 2.
4. **Deduplication**: Finally, we filter by `chunk_id` to remove duplicate results returned by both indices.

## 4.4 Agentic Workflow: Planning, Retrieval and Reasoning

The system implements the LangGraph workflow [19] as shown in the pseudo-code below:

```python
def agentic_flow(query):
    # Planner uses regex to classify query type
    state = Planner.classify(query)
    
    # Hybrid search across BM25 and Vector indices
    chunks = Retriever.hybrid_search(state.sub_queries)
    
    # Conditional logic based on evidence threshold (e.g., score > 0.3)
    if Router.needs_more_evidence(state, chunks):
        chunks += SecondRetriever.search(state.missing_sub_queries)
        
    # Synthesis using DeepSeek Reasoner
    answer = ReasoningAgent.synthesize(state, chunks)
    
    # Format with rule-specific citations
    return CitationFormatter.format(answer, chunks)
```

The `Planner` employs heuristic classification: if the query contains multi-part requirements (e.g., "and", "or", "both"), it is flagged as `multi_hop`. Otherwise, it defaults to `direct`. The `ReasoningAgent` prompt explicitly mandates that the LLM verify the alignment between its generated claims and the retrieved chunks, adding an "Uncertainty Note" if evidence coverage is partial.

## 4.5 Current Limitations and Planned Enhancements

As an MVP, the system has limitations that will be addressed in Phase 2:

1. **Heuristic Planner**: Currently rule-based; we intend to shift to LLM-driven planning for better query understanding.
2. **Evidence Coverage**: Second retrieval is triggered by simple relevance thresholds; this will be upgraded to an evidence-coverage checking model [12].
3. **Tool Integration**: While the interface is implemented, we have not yet integrated external tools such as financial calculators.
4. **Memory and Context**: The system is stateless. Adding conversational memory will be a priority.
5. **Formal Evaluation**: Rigorous evaluation using RAGAS is scheduled for the next phase.

