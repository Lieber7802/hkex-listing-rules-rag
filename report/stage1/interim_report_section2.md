# 2. Related Work

To understand how our system fits into the broader landscape of compliance question answering, we review four areas of related work. We begin with traditional information retrieval methods, which provide the foundation for keyword-based search. We then discuss neural and dense retrieval approaches, which improve semantic recall. Next, we examine the evolution from standard RAG to Agentic RAG systems. Finally, we position our work relative to these existing approaches and acknowledge the current limitations of our Phase 1 prototype.

## 2.1 Traditional Information Retrieval for Regulatory Documents

Traditional information retrieval systems, such as keyword-based search and the BM25 algorithm, have long been the backbone of regulatory document retrieval [13, 14]. These systems rely on inverted indexes to match user queries with terms appearing in the document corpus.

The main advantage of these methods is their stability and speed. Because they are based on literal term matching, they provide high interpretability; users can clearly see why a specific document was retrieved based on the occurrence of their search terms. For many legal and compliance tasks, this deterministic nature is a significant benefit, as it minimizes the risk of the system retrieving irrelevant content when no keyword match exists, though it risks missing relevant documents that use different wording.

However, traditional IR systems have critical limitations for complex regulatory scenarios like the HKEX Listing Rules. First, they lack semantic understanding. A query like "disclosure requirements for connected transactions" may fail to retrieve relevant documents if the documents use synonyms or related terms not explicitly present in the query. Second, they struggle with multi-hop questions. When a query requires synthesizing information from multiple provisions — for instance, checking both disclosure thresholds and shareholder approval rules — a keyword-based system can only retrieve individual fragments, leaving the user to manually piece them together. This limitation often requires multiple rounds of query refinement, which is time-consuming and prone to error.

## 2.2 Neural and Dense Retrieval Methods

To address the limitations of keyword matching, researchers have increasingly turned to dense retrieval methods using neural networks [15]. These approaches map queries and documents into a shared continuous vector space, where semantic similarity is measured by distance (e.g., cosine similarity).

Dense retrieval excels at capturing semantic relationships. By representing the underlying meaning of text, models like BERT [16] or more specialized embedding models such as BGE can retrieve documents that are semantically relevant even if they share no common keywords with the query. When paired with vector databases like FAISS or Chroma, these systems can perform fast approximate nearest neighbor searches on large datasets.

Despite this advantage, dense retrieval has its own drawbacks in legal domains. Because the matching process relies on learned embeddings, it can occasionally retrieve semantically similar content that is legally imprecise for the specific query. In high-stakes environments like HKEX compliance, where the precision of rule interpretation matters, semantic similarity does not always guarantee legal correctness. A retrieved chunk might be about connected transactions but actually describe an unrelated exemption, which could mislead the system into suggesting an incorrect rule.

## 2.3 RAG and Agentic RAG Systems

Retrieval-Augmented Generation (RAG) improves upon pure LLM generation by grounding answers in external, retrieved evidence [17]. A standard RAG pipeline typically involves a single-pass retrieval followed by a generation step. While effective for simple fact retrieval, it remains passive and often inadequate for complex compliance questions that require reasoning across multiple documents.

Agentic RAG represents a shift toward more autonomous systems [18]. Unlike a standard RAG pipeline, an Agentic RAG system uses a planner to break down a user's question, execute multiple rounds of retrieval, and synthesize evidence in a reasoned way. This is particularly useful for legal and regulatory domains. For example, if a compliance query needs clarification, an agent can automatically perform a second round of targeted searching. Frameworks like LangChain and LangGraph facilitate this by allowing the definition of stateful workflows, where the system maintains context and makes iterative decisions about what information is still needed [19].

Recent research shows that this agentic paradigm is better suited for complex Q&A because it shifts the system from a one-shot responder to an iterative reasoner. By separating the roles of planning, retrieval, and reasoning, these systems can check whether they have sufficient evidence before generating a final answer. If the agent determines that the evidence is insufficient or contradictory, it can choose to backtrack or rephrase the query. This degree of control is essential for accurate compliance advising, where a single missed provision can lead to incorrect guidance.

## 2.4 Relationship Between Existing Work and This Project

Our system integrates both traditional and neural retrieval. We use a hybrid approach that combines BM25 for precise keyword matching and dense embeddings for semantic recall. This balances the need for lexical exactness with the ability to handle synonyms and paraphrased queries.

Beyond retrieval, our system extends standard RAG by introducing a planner and a conditional router. This allows the system to distinguish between simple rule lookups and multi-hop compliance questions, triggering a second retrieval step only when necessary. Each answer includes citations with rule numbers and source document identifiers, which is a requirement for compliance use cases where answer provenance must be traceable.

That said, the current prototype has clear limitations. The planner relies on simple heuristic classification rather than full LLM-driven reasoning. The system does not yet support tool use (such as financial calculators), session memory, or formal evaluation. These are planned for Phase 2. At this stage, the system is best understood as a domain-specific Agentic RAG prototype for HKEX compliance — more capable than a standard single-pass RAG system, but still an early-stage implementation focused on validating the core agentic workflow.
