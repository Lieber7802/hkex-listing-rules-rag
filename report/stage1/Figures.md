# Figures for Interim Report

## Figure 1: System Architecture Diagram

```mermaid
flowchart TB
    subgraph Offline["Offline Processing"]
        A[/"📄 Raw Documents<br/>(PDF/TXT/MD)"/] --> B["Document Ingestion"]
        B --> C["Cleaning & Normalization"]
        C --> D["Structure-Aware Chunking"]
        D --> E["Dual Indexing"]
        
        subgraph Indexes[" "]
            direction LR
            F[("BM25<br/>Index")]
            G[("FAISS<br/>Vector Index")]
        end
        E --> F
        E --> G
    end
    
    subgraph Online["Online Query Processing"]
        H[/"💬 User Query"/] --> I["Planner<br/>(Classify & Decompose)"]
        I --> J["Hybrid Retriever"]
        F -.-> J
        G -.-> J
        J --> K{"Evidence<br/>Sufficient?"}
        K -->|No| L["Second Retrieval"]
        K -->|Yes| M["Reasoning Agent"]
        L --> M
        M --> N["Citation Formatter"]
        N --> O[/"📋 Structured Response<br/>(Answer + Citations)"/]
    end
    
    style Offline fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style Online fill:#fff8e1,stroke:#ff8f00,stroke-width:2px
    style A fill:#bbdefb
    style H fill:#ffe0b2
    style O fill:#c8e6c9
    style K fill:#fff9c4,stroke:#f9a825
```

**Figure 1: System Architecture Overview**
- The system consists of two main phases: offline document processing (blue) and online query processing (yellow)
- Offline phase: Documents are ingested, cleaned, chunked with structure preservation, and indexed using both BM25 and dense embeddings
- Online phase: User queries flow through a planner, hybrid retriever, optional second retrieval, reasoning agent, and citation formatter
- Dashed lines indicate index access during retrieval

---

## Figure 2: LangGraph Workflow Diagram

```mermaid
flowchart TB
    START((START)) --> Planner
    
    subgraph Nodes["Processing Nodes"]
        Planner["🧠 Planner Node<br/><small>Classify: direct / multi_hop<br/>Decompose complex queries</small>"]
        
        Retriever["🔍 Retriever Node<br/><small>Hybrid search: BM25 + Dense<br/>Merge and rank results</small>"]
        
        Router{"🔀 Conditional Router<br/><small>Check evidence coverage</small>"}
        
        SecondRetrieval["🔄 Second Retrieval<br/><small>Query reformulation<br/>Fill evidence gaps</small>"]
        
        Reasoning["💡 Reasoning Node<br/><small>Synthesize answer<br/>Ground in evidence</small>"]
        
        CitationFormatter["📝 Citation Formatter<br/><small>Format rule references<br/>Validate traceability</small>"]
    end
    
    Planner --> Retriever
    Retriever --> Router
    Router -->|Insufficient| SecondRetrieval
    Router -->|Sufficient| Reasoning
    SecondRetrieval --> Reasoning
    Reasoning --> CitationFormatter
    CitationFormatter --> END((END))
    
    subgraph State["Workflow State (GraphState)"]
        direction LR
        S1["query: str"]
        S2["query_type: str"]
        S3["sub_queries: List"]
        S4["retrieved_chunks: List"]
        S5["needs_second_retrieval: bool"]
        S6["answer: str"]
        S7["citations: List"]
    end
    
    style START fill:#a5d6a7,stroke:#2e7d32
    style END fill:#a5d6a7,stroke:#2e7d32
    style Router fill:#fff59d,stroke:#f9a825,stroke-width:2px
    style State fill:#fafafa,stroke:#757575,stroke-dasharray: 5 5
    style Nodes fill:#ffffff,stroke:#e0e0e0
```

**Figure 2: LangGraph Agent Workflow**
- The workflow uses LangGraph StateGraph for conditional branching
- **Planner**: Classifies queries and decomposes multi-hop questions
- **Retriever**: Performs hybrid search across both indexes
- **Conditional Router**: Decides whether second retrieval is needed based on evidence coverage
- **Reasoning**: Generates citation-grounded answers using DeepSeek Reasoner
- **State**: Maintains query context, retrieved chunks, and intermediate results across nodes

---

## Notes for Figure Rendering

**Figure 1 Rendering Tips:**
- Use TB (top-bottom) layout for better fit in A4/Letter paper
- Recommended width: 500-600px (fits single column)
- Blue region = offline processing, Yellow region = online processing
- Export as PNG/SVG at 150-200 DPI for print quality

**Figure 2 Rendering Tips:**
- Recommended width: 450-550px
- The State box shows data that flows through the workflow
- Green circles = entry/exit points
- Yellow diamond = decision point
- Export as PNG/SVG at 150-200 DPI for print quality

**Mermaid Export Instructions:**
1. Go to https://mermaid.live/
2. Paste the code block
3. Click "Download PNG" or "Download SVG"
4. For Word: Insert → Pictures → select the downloaded file
5. Recommended DPI: 150-200 for clear print output
