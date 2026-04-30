# 中期报告文字风格修改建议

## 总体评价

当前报告的主要问题：
1. **过于完美的句式结构** - 每个句子都很流畅，缺少非母语者的自然停顿和小瑕疵
2. **AI写作特征明显** - 大量使用"specifically", "notably", "essentially"等连接词
3. **过度使用被动语态** - 显得过于正式和机械
4. **缺少个人语气** - 没有"we found", "we noticed"等第一人称表达

---

## Section 1: Introduction

### 1.1 Background and Problem Context

**原文：**
> Traditional keyword search can find specific rules, but it fails when dealing with this complexity. It cannot understand legal terminology, handle multi-step reasoning, or identify implicit cross-references between chapters.

**问题：** 句式过于完美，三个并列短语过于工整

**修改建议：**
> Traditional keyword search can find specific rules, but it fails when dealing with this complexity. It cannot understand legal terminology or handle multi-step reasoning, and identifying implicit cross-references between chapters is also difficult.

---

**原文：**
> This motivates the need for more intelligent tools that can provide accurate and evidence-based answers to compliance questions, such as Retrieval-Augmented Generation (RAG) systems with agent planning capabilities.

**问题：** 句子过长且过于流畅，"motivates the need"是AI常用表达

**修改建议：**
> This shows we need more intelligent tools for compliance questions. Retrieval-Augmented Generation (RAG) systems with agent planning capabilities could provide accurate and evidence-based answers.

---

### 1.2 Project Objectives

**原文：**
> This project builds an Agentic Retrieval-Augmented Generation (RAG) system for HKEX Listing Rules compliance questions. Standard RAG systems search and retrieve information once. Our system adds agentic planning and multi-step reasoning to handle the complex structure of regulatory documents [5].

**问题：** 过于简洁完美，缺少自然的解释性语言

**修改建议：**
> This project builds an Agentic Retrieval-Augmented Generation (RAG) system for HKEX Listing Rules compliance questions. Standard RAG systems only search and retrieve information once, which is not enough for complex regulatory documents. Our system adds agentic planning and multi-step reasoning to handle this complexity [5].

---

**原文：**
> The system handles both simple rule lookups and complex questions that require combining multiple rules [7].

**问题：** 过于简洁

**修改建议：**
> The system can handle both simple rule lookups and more complex questions that need to combine multiple rules [7].

---

### 1.3 Practical Value and Expected Outcome

**原文：**
> This system is designed to assist compliance professionals, not replace them.

**问题：** 过于正式和完美

**修改建议：**
> This system is designed to help compliance professionals, not to replace them.

---

**原文：**
> By automating the retrieval and initial synthesis of relevant rules, the system reduces the time spent on manual document searches.

**问题：** "By automating...the system reduces"是典型AI句式

**修改建议：**
> The system automates the retrieval and initial synthesis of relevant rules, which can reduce the time spent on manual document searches.

---

**原文：**
> In the longer term, this work contributes to the broader goal of building intelligent compliance advisory systems.

**问题：** "contributes to the broader goal"是AI常用表达

**修改建议：**
> In the longer term, this work can help build more intelligent compliance advisory systems.

---

## Section 2: Related Work

### 2.1 Traditional Information Retrieval

**原文：**
> Traditional information retrieval systems rely on lexical matching. The most widely used algorithm is BM25, a probabilistic ranking function that scores documents based on term frequency and inverse document frequency [6].

**问题：** 过于教科书式

**修改建议：**
> Traditional information retrieval systems rely on lexical matching. BM25 is the most widely used algorithm. It is a probabilistic ranking function that scores documents based on term frequency and inverse document frequency [6].

---

**原文：**
> These systems work well when the query and document share exact keywords, but they struggle with synonyms, paraphrasing, and conceptual similarity.

**问题：** 句式过于完美

**修改建议：**
> These systems work well when the query and document share exact keywords. But they have problems with synonyms, paraphrasing, and conceptual similarity.

---

### 2.2 Neural and Dense Retrieval Methods

**原文：**
> Dense retrieval methods address these limitations by representing queries and documents as vectors in a shared semantic space.

**问题：** "address these limitations"是AI常用表达

**修改建议：**
> Dense retrieval methods try to solve these problems by representing queries and documents as vectors in a shared semantic space.

---

**原文：**
> Models like BERT [14] or specialized embedding models can capture the underlying meaning of text, even when different words are used.

**问题：** 过于流畅

**修改建议：**
> Models like BERT [14] or specialized embedding models can capture the meaning of text even when different words are used.

---

### 2.3 RAG and Agentic RAG Systems

**原文：**
> RAG systems combine retrieval with generation by grounding answers in external, retrieved evidence [15].

**问题：** "by grounding answers in"是学术套话

**修改建议：**
> RAG systems combine retrieval with generation. They use external retrieved evidence to generate answers [15].

---

**原文：**
> Agentic RAG represents a shift toward more autonomous systems [17].

**问题：** "represents a shift toward"是AI常用表达

**修改建议：**
> Agentic RAG is a step toward more autonomous systems [17].

---

**原文：**
> By separating the roles of planning, retrieval, and reasoning, these systems can check whether they have sufficient evidence before generating a final answer.

**问题：** 句子过长且过于完美

**修改建议：**
> These systems separate planning, retrieval, and reasoning into different roles. This allows them to check whether they have enough evidence before generating a final answer.

---

### 2.4 Relationship Between Existing Work and This Project

**原文：**
> Our system integrates both traditional and neural retrieval. We use a hybrid approach that combines BM25 for precise keyword matching and dense embeddings for semantic recall.

**问题：** 过于简洁完美

**修改建议：**
> Our system integrates both traditional and neural retrieval methods. We use a hybrid approach that combines BM25 for precise keyword matching and dense embeddings for semantic recall.

---

**原文：**
> Beyond retrieval, our system extends standard RAG by introducing a planner and a conditional router.

**问题：** "Beyond retrieval"是AI常用过渡

**修改建议：**
> Besides retrieval, our system extends standard RAG by adding a planner and a conditional router.

---

**原文：**
> At this stage, the system is best understood as a domain-specific Agentic RAG prototype for HKEX compliance — more capable than a standard single-pass RAG system, but still an early-stage implementation focused on validating the core agentic workflow.

**问题：** 句子过长，"is best understood as"是AI表达

**修改建议：**
> At this stage, the system is a domain-specific Agentic RAG prototype for HKEX compliance. It is more capable than a standard single-pass RAG system, but it is still an early-stage implementation. The focus is on validating the core agentic workflow.

---

## Section 3: System Modeling and Structure

### 3.1 Problem Scope and System Boundary

**原文：**
> We chose these areas because they come up frequently in compliance questions and involve cross-referencing between multiple rule provisions.

**问题：** "come up frequently"口语化但不够学术

**修改建议：**
> We chose these areas because they appear frequently in compliance questions and involve cross-referencing between multiple rule provisions.

---

### 3.2 Overall Architecture

**原文：**
> The system follows a pipeline with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation.

**问题：** 过于简洁

**修改建议：**
> The system follows a pipeline architecture with six stages: Document Ingestion, Cleaning, Chunking, Indexing, Query Processing, and Response Generation.

---

**原文：**
> Chunking preserves document structure: instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers, then creates chunks that keep these elements intact.

**问题：** 冒号后的解释过长

**修改建议：**
> Chunking preserves document structure. Instead of splitting at arbitrary token boundaries, the chunker identifies rule numbers, section titles, and chapter markers. Then it creates chunks that keep these elements intact.

---

### 3.3 LangGraph Workflow Structure

**原文：**
> Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph allows conditional branching based on intermediate results.

**问题：** 过于简洁完美

**修改建议：**
> Query processing uses LangGraph to implement a stateful agent workflow. Unlike a hardcoded pipeline, LangGraph can do conditional branching based on intermediate results.

---

**原文：**
> Classification uses heuristic rules based on keyword patterns, checking for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

**问题：** 句子过长

**修改建议：**
> Classification uses heuristic rules based on keyword patterns. It checks for conjunctions like "and" or "or" and phrases that indicate cross-referencing needs.

---

### 3.4 Design Justifications

**原文：**
> Several key design choices shaped the architecture.

**问题：** "shaped the architecture"是AI表达

**修改建议：**
> Several key design choices were made for the architecture.

---

**原文：**
> By preserving rule numbers and section titles in chunk metadata, we enable more precise retrieval and citation generation.

**问题：** "By preserving...we enable"是AI句式

**修改建议：**
> We preserve rule numbers and section titles in chunk metadata. This enables more precise retrieval and citation generation.

---

## Section 4: Methodology and Algorithms

### 4.1 Knowledge Base Construction Pipeline

**原文：**
> The pipeline consists of four stages, each designed to preserve the structure and semantics of the original documents.

**问题：** "each designed to"是AI表达

**修改建议：**
> The pipeline consists of four stages. Each stage is designed to preserve the structure and semantics of the original documents.

---

### 4.2 Structure-Aware Chunking Algorithm

**原文：**
> Splitting text by token count often fails in legal documents. It might cut a rule in half or separate it from its context.

**问题：** 过于简洁完美

**修改建议：**
> Splitting text by token count often fails in legal documents because it might cut a rule in half or separate it from its context.

---

### 4.3 Hybrid Retrieval Strategy

**原文：**
> We combine lexical and semantic search to maximize retrieval robustness [13, 14].

**问题：** "to maximize retrieval robustness"过于正式

**修改建议：**
> We combine lexical and semantic search to improve retrieval robustness [13, 14].

---

### 4.5 Current Limitations and Planned Enhancements

**原文：**
> As an MVP, the system has limitations that will be addressed in Phase 2:

**问题：** 过于简洁

**修改建议：**
> As an MVP (Minimum Viable Product), the system has some limitations that will be addressed in Phase 2:

---

## Section 5: Preliminary Performance Analysis

### 5.1 Experimental Setup

**原文：**
> This section reports early-stage feasibility testing, not a comprehensive benchmark evaluation.

**问题：** 过于正式

**修改建议：**
> This section reports early-stage feasibility testing. It is not a comprehensive benchmark evaluation.

---

### 5.2 Functional Verification

**原文：**
> Key verifications include: documents are ingested and chunks are generated with correct metadata fields, BM25 and FAISS indexes build without errors, the hybrid retriever returns ranked results with fused scores, the API endpoint accepts queries and returns structured JSON responses, and citations in the output are traceable to specific chunk IDs and rule numbers.

**问题：** 句子过长，列举过于完美

**修改建议：**
> Key verifications include:
> - Documents are ingested and chunks are generated with correct metadata fields
> - BM25 and FAISS indexes build without errors
> - The hybrid retriever returns ranked results with fused scores
> - The API endpoint accepts queries and returns structured JSON responses
> - Citations in the output are traceable to specific chunk IDs and rule numbers

---

## Section 6: Milestones and Overall Schedule

### 6.1 Work Completed So Far

**原文：**
> Phase 1 focused on building a functional backend prototype. Our work can be summarized in three areas:

**问题：** "can be summarized in"是AI表达

**修改建议：**
> Phase 1 focused on building a functional backend prototype. Our work includes three main areas:

---

## Section 7: Work to be Completed

### 7.1 Technical Improvements

**原文：**
> The score fusion strategy will be upgraded from weighted linear combination to Reciprocal Rank Fusion (RRF), which is more robust to score distribution differences.

**问题：** 句子过长

**修改建议：**
> The score fusion strategy will be upgraded from weighted linear combination to Reciprocal Rank Fusion (RRF). RRF is more robust to score distribution differences.

---

### 7.2 Evaluation and Reporting Work

**原文：**
> Formal evaluation is essential for validating the system's performance in a regulatory compliance context.

**问题：** "is essential for validating"是AI表达

**修改建议：**
> Formal evaluation is essential to validate the system's performance in a regulatory compliance context.

---

## 总结

### 主要修改方向：

1. **拆分长句** - 将复杂句拆成2-3个简单句
2. **减少完美并列** - 避免过于工整的三项并列
3. **替换AI套话** - 
   - "motivates the need" → "shows we need"
   - "represents a shift" → "is a step"
   - "address limitations" → "solve problems"
   - "by doing X, we achieve Y" → "We do X. This achieves Y."
4. **增加自然停顿** - 用句号代替逗号和分号
5. **简化连接词** - "Beyond" → "Besides", "Specifically" → 删除
6. **保留小瑕疵** - 偶尔用"can"代替"is able to"，用"help"代替"assist"

### 不需要修改的地方：

- 技术术语（BM25, FAISS, LangGraph等）
- 引用格式
- 表格和图表说明
- 代码片段
