# 中期报告文字风格修改建议 - Section 1-2 (Humanized)

## Section 1: Introduction

### 1.1 Background and Problem Context

**修改建议：**
> The Hong Kong Stock Exchange (HKEX) is one of the world's major financial markets, with over 2,600 listed companies and a market capitalization exceeding HKD 30 trillion as of 2025 [1]. Listed companies must comply with the HKEX Listing Rules. The Main Board Listing Rules include over 30 chapters and more than 2,500 individual provisions, along with many appendices and guidance materials [2]. The Growth Enterprise Market (GEM) uses a similar rulebook. HKEX also provides supplementary materials like Guidance Letters, Listing Decisions, and Frequently Asked Questions to help issuers interpret these rules [3].
>
> These documents are heavily cross-referenced. To understand the requirements for a connected transaction, a company might need to check Chapter 14A (Connected Transactions), Chapter 14 (Notifiable Transactions), Chapter 2 (Definitions), and several guidance letters. Each rule often points to other sub-rules or exceptions. As a result, company secretaries and legal advisors often find it hard to locate all relevant provisions and reach a clear conclusion [4].
>
> Traditional keyword search can find specific rules, but it fails when dealing with this complexity. It cannot understand legal terminology or handle multi-step reasoning. Identifying implicit cross-references between chapters is also difficult. Practitioners spend considerable time manually tracing these connections, which increases the risk of missing important obligations. So we need more intelligent tools for compliance questions. Retrieval-Augmented Generation (RAG) systems with agent planning capabilities could provide accurate and evidence-based answers.

---

### 1.2 Project Objectives

**修改建议：**
> This project builds an Agentic Retrieval-Augmented Generation (RAG) system for HKEX Listing Rules compliance questions. Standard RAG systems usually retrieve information in a single pass, which is not enough for complex regulatory documents. Our system adds agentic planning and multi-step reasoning to better handle this complexity [5].
>
> The primary objectives for Phase 1 are:
>
> 1. Document Ingestion: Import HKEX documents (Main Board, GEM, and guidance materials), perform structure-aware chunking that preserves rule numbers and chapter titles, and build a search index using both keyword (BM25) and semantic (embedding) methods [6].
> 2. Agentic Workflow Prototype: Build a workflow using LangGraph with three components: a Planner to classify questions, a retriever to find relevant information, and a reasoning component to synthesize answers. The system can handle both simple rule lookups and more complex questions that need to combine multiple rules [7].
> 3. Citation-Grounded Answers: Every answer is supported by evidence from the rules. Each answer includes clear citations with rule numbers and chapter titles. This is important for compliance tasks, where evidence needs to be verifiable [8].
> 4. Backend API: Develop a FastAPI backend with a modular architecture. This makes it easier to add new features later, such as specialized compliance tools, frontend interfaces, or evaluation datasets [9].
>
> Phase 1 will not include: a web interface, specialized calculators, a full benchmark dataset, formal evaluation frameworks, or production-level deployment. We focus on building a functional backend prototype to validate our approach.

---

### 1.3 Practical Value and Expected Outcome

**修改建议：**
> Compliance officers, company secretaries, and legal advisors often spend hours searching through multiple chapters and guidance documents. Our system automatically locates relevant rules, traces cross-references, and provides answers with citations. This saves time and helps reduce the risk of missing important regulatory obligations [10].
>
> This project also investigates how information systems can reason about legal documents, rather than just matching keywords. It could lead to more advanced tools later, like automated disclosure checkers or systems that provide scenario-based advice [11].
>
> Phase 1 aims to deliver:
>
> 1. Functional Backend Prototype: A Python application that can ingest HKEX documents, index them, and provide compliance answers via a RESTful API.
> 2. Knowledge Pipeline: A structured workflow that processes regulatory documents, preserves their hierarchy, and enables precise retrieval.
> 3. Preliminary Validation: Initial testing to prove that the system can handle both simple and multi-hop compliance questions and return answers backed by traceable sources.
> 4. Architectural Foundation: A modular design that allows for easy integration of new tools, frontends, and evaluation methods in the next phase [12].

---

## Section 2: Related Work

### 2.1 Traditional Information Retrieval

**修改建议：**
> Traditional information retrieval systems, like keyword-based search and the BM25 algorithm, are commonly used for regulatory document retrieval [13, 14]. These systems use inverted indexes to match user queries with terms in the documents.
>
> The main advantage of these methods is their stability and speed. Because they are based on literal term matching, they provide high interpretability; users can clearly see why a specific document was retrieved based on the occurrence of their search terms. For many legal and compliance tasks, this deterministic nature is a significant benefit, as it minimizes the risk of the system "hallucinating" relevance where none exists.
>
> However, traditional IR systems have limitations in complex scenarios like the HKEX Listing Rules. For one, they lack semantic understanding. If a user queries "disclosure requirements for connected transactions," the system may fail to find relevant documents if they use synonyms or different terms that are not in the query. For another, they struggle with multi-hop questions. When a query requires synthesizing information from multiple provisions—for instance, checking both disclosure thresholds and shareholder approval rules—a keyword-based system can only retrieve individual fragments. The user is then left to manually piece them together, which is time-consuming and prone to error.

---

### 2.2 Neural and Dense Retrieval Methods

**修改建议：**
> Dense retrieval methods try to solve these problems by representing queries and documents as vectors in a shared semantic space.
>
> Dense retrieval excels at capturing semantic relationships. Models like BERT [16] or specialized embedding models can capture the meaning of text even when different words are used. When paired with vector databases like FAISS or Chroma, these systems can perform fast approximate nearest neighbor searches on large datasets.
>
> However, dense retrieval is not perfect. It can retrieve semantically similar but factually irrelevant results. For example, a query about "connected transactions" might retrieve chunks about "related party transactions," even though the legal definitions are different. This means a hybrid approach that combines lexical precision with semantic recall is often more appropriate for regulatory retrieval tasks.

---

### 2.3 RAG and Agentic RAG Systems

**修改建议：**
> Retrieval-Augmented Generation (RAG) systems combine retrieval with generation. They use external retrieved evidence to generate answers [17]. A standard RAG pipeline first retrieves relevant documents, then passes them to a language model to generate a response. While effective for simple fact retrieval, it remains passive and often inadequate for complex compliance questions that require reasoning across multiple documents.
>
> Agentic RAG is a step toward more autonomous systems [18]. Unlike a standard RAG pipeline, an Agentic RAG system uses a planner to break down a user's question, run multiple retrieval steps, and then synthesize the evidence. This is particularly useful for legal and regulatory domains. For example, if a compliance query needs clarification, an agent can automatically perform a second round of targeted searching. Frameworks like LangChain and LangGraph can implement this through stateful workflows. The system maintains context and can make iterative decisions about what information is still needed [19].
>
> Recent research shows this approach works better for complex Q&A. It changes the system from a "one-shot" responder into one that can reason iteratively. These systems separate planning, retrieval, and reasoning into different roles. This allows them to check whether they have enough evidence before generating a final answer. If the agent determines that the evidence is insufficient or contradictory, it can choose to backtrack or rephrase the query. This degree of control is essential for accurate compliance advising, where a single missed provision can lead to incorrect guidance.

---

### 2.4 Relationship Between Existing Work and This Project

**修改建议：**
> Our system integrates both traditional and neural retrieval methods. We use a hybrid approach that combines BM25 for precise keyword matching and dense embeddings for semantic recall. This can balance the need for lexical exactness and the ability to handle synonyms and paraphrased queries.
>
> Besides retrieval, our system extends standard RAG by adding a planner and a conditional router. This allows the system to distinguish between simple rule lookups and multi-hop compliance questions. The system will trigger a second retrieval step only when it is necessary. Each answer includes citations with rule numbers and source document identifiers. This is important for compliance use cases because we need to trace where the answer comes from.
>
> However, the current prototype has clear limitations. The planner uses simple heuristic classification instead of full LLM-driven reasoning. The system does not yet support tool use (such as financial calculators), session memory, or formal evaluation. We plan to add these in Phase 2. At this stage, the system is a domain-specific Agentic RAG prototype for HKEX compliance. It is more capable than a standard single-pass RAG system, but it is still an early-stage implementation. The main goal now is to validate the core agentic workflow.