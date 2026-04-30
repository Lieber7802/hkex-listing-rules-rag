# 1. Introduction

## 1.1 Background and Problem Context

The Hong Kong Stock Exchange (HKEX) is a major global financial market, with over 2,600 listed companies and a market capitalization of more than HKD 30 trillion as of 2025 [1]. Companies listed on the exchange must follow the HKEX Listing Rules. The Main Board Listing Rules contain over 30 chapters and more than 2,500 specific rules, plus extensive appendices and guidance materials [2]. The Growth Enterprise Market (GEM) has a similar rulebook. HKEX also publishes supplementary materials including Guidance Letters, Listing Decisions, and Frequently Asked Questions to help interpret these rules [3].

These documents are heavily cross-referenced. A company trying to understand the requirements for a connected transaction might need to check Chapter 14A (Connected Transactions), Chapter 14 (Notifiable Transactions), Chapter 2 (Definitions), and several guidance letters. Each rule can point to other sub-rules or exceptions. Company secretaries and legal advisors often struggle to locate all relevant provisions and reach a clear conclusion [4].

Traditional keyword search can find specific rules, but it fails when dealing with this complexity. It cannot understand legal terminology, handle multi-step reasoning, or identify implicit cross-references between chapters. Practitioners spend considerable time manually tracing these connections, which increases the risk of missing important obligations. This motivates the need for more intelligent tools that can provide accurate and evidence-based answers to compliance questions, such as Retrieval-Augmented Generation (RAG) systems with agent planning capabilities.

## 1.2 Project Objectives

This project builds an Agentic Retrieval-Augmented Generation (RAG) system for HKEX Listing Rules compliance questions. Standard RAG systems search and retrieve information once. Our system adds agentic planning and multi-step reasoning to handle the complex structure of regulatory documents [5].

Phase 1 has four main objectives:

1. **Document Ingestion**: Import HKEX documents (Main Board, GEM, and guidance materials), perform structure-aware chunking that preserves rule numbers and chapter titles, and build a search index using both keyword (BM25) and semantic (embedding) methods [6].

2. **Agentic Workflow Prototype**: Build a workflow using LangGraph with three components: a Planner to classify questions, a retriever to find relevant information, and a reasoning component to synthesize answers. The system handles both simple rule lookups and complex questions that require combining multiple rules [7].

3. **Citation-Grounded Answers**: Every answer must be supported by evidence from the rules. Each answer includes clear citations with rule numbers and chapter titles, which is necessary for compliance tasks where evidence must be verifiable [8].

4. **Backend API**: Develop a FastAPI backend with a modular architecture. This makes it easier to add new features later, such as specialized compliance tools, frontend interfaces, or evaluation datasets [9].

Phase 1 does not include: a web interface, specialized calculators, a full benchmark dataset, formal evaluation frameworks, or production-level deployment. We focus on building a functional backend prototype to validate the approach.

## 1.3 Practical Value and Expected Outcome

Compliance officers, company secretaries, and legal advisors often spend hours searching for information across multiple chapters and guidance documents. This system can help by automatically locating relevant rules, tracing cross-references, and providing cited answers. This reduces both time spent and the risk of missing important obligations [10].

The project also explores how information systems can reason about legal documents instead of just matching keywords. This could support more advanced tools in the future, such as automated disclosure checkers or scenario-based advisory systems [11].

Phase 1 aims to deliver:

1. **Functional Backend Prototype**: A Python application that ingests HKEX documents, indexes them, and provides compliance answers via a RESTful API.

2. **Knowledge Pipeline**: A workflow that processes regulatory documents while preserving their hierarchy for precise retrieval.

3. **Preliminary Validation**: Initial tests showing the system can handle both simple and multi-hop compliance questions with traceable source citations.

4. **Architectural Foundation**: A modular design that supports integration of new tools, frontends, and evaluation methods in Phase 2 [12].
