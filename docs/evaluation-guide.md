# HKEX Agentic RAG — Benchmark 评估体系设计指南

> 本文档面向项目开发者，详细讲解如何为本项目构建评估数据集和评估框架。
> 涵盖：评估目标、评估指标、评估原理、数据集定义、数据集获取与制作方法。

---

## 目录

1. [评估的目标是什么](#1-评估的目标是什么)
2. [评估指标体系](#2-评估指标体系)
3. [评估原理](#3-评估原理)
4. [数据集如何定义](#4-数据集如何定义)
5. [数据集如何获取和制作](#5-数据集如何获取和制作)
6. [评估流程设计](#6-评估流程设计)
7. [与 RAGAS 的关系](#7-与-ragas-的关系)
8. [实施路线图](#8-实施路线图)

---

## 1. 评估的目标是什么

### 1.1 为什么需要评估

本项目是一个 **Agentic RAG** 系统，它的回答质量取决于多个环节的协作：

```
Planner → Retriever → Coverage → Evidence → Reasoning → Verifier
```

任何一个环节出错都会导致最终答案质量下降。评估的目的是：

1. **量化系统质量** — 用数字说话，不是"感觉还行"
2. **定位瓶颈** — 到底是检索不够好，还是推理不够好？
3. **驱动优化** — 改了代码后，质量是变好了还是变差了？
4. **支撑论文** — 研究报告需要实验数据和对比结果

### 1.2 本项目评估的三个层次

```
┌─────────────────────────────────────────────────────────────┐
│                  评估三层架构                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: 组件级评估 (Component Evaluation)                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  • Planner 分类准确率                                  │  │
│  │  • Retriever 召回率 / 精确率                            │  │
│  │  • Coverage Checker 判断准确性                          │  │
│  │  • Tool 调用正确性                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Layer 2: 管道级评估 (Pipeline Evaluation)                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  • 检索到的 chunks 是否覆盖了答案所需的全部规则         │  │
│  │  • 引用是否正确指向了实际使用的证据                     │  │
│  │  • 整体端到端延迟                                      │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  Layer 3: 答案级评估 (Answer Evaluation)                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  • 答案是否正确 (Correctness)                          │  │
│  │  • 答案是否完整 (Completeness)                         │  │
│  │  • 答案是否忠实于证据 (Faithfulness)                    │  │
│  │  • 引用质量 (Citation Quality)                         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 评估对论文/报告的支撑

在 Final Report 中，你需要回答这些问题：

| 论文需要回答的问题 | 需要的评估支撑 |
|---|---|
| "系统能否正确回答合规问题？" | 答案正确率 + 完整度 |
| "Agentic 比 naive RAG 好在哪？" | 对比实验: Agentic RAG vs 单轮检索 |
| "多跳推理有效吗？" | multi_hop 类型的召回率和答案质量 |
| "Tool 有用吗？" | 有 tool vs 无 tool 的准确率对比 |
| "系统有什么不足？" | 错误分析 (error taxonomy) |

---

## 2. 评估指标体系

### 2.1 检索质量指标

| 指标 | 定义 | 计算方法 | 本项目含义 |
|------|------|----------|-----------|
| **Recall@K** | 在 top-K 结果中，覆盖了多少个"应该找到"的 chunks | `找到的相关chunks数 / 总共应该找到的chunks数` | 系统是否能把所有相关规则都检索出来 |
| **Precision@K** | 在 top-K 结果中，有多少是真正相关的 | `相关chunks数 / K` | 检索结果中噪音多不多 |
| **MRR** | 第一个相关结果出现在第几位 | `1 / 第一个相关结果的排名` | 最相关的规则是否排在前面 |
| **Context Relevance** | 检索到的 context 与问题的相关程度 | LLM 判断或人工标注 | 检索上下文是否对回答有帮助 |

**本项目特有的检索指标：**

| 指标 | 定义 |
|------|------|
| **Rule Coverage** | 答案需要引用的规则编号，是否都被检索到了 |
| **Cross-reference Coverage** | 对于需要多个章节的问题，是否检索到了所有涉及的章节 |

### 2.2 答案质量指标

| 指标 | 定义 | 计算方法 |
|------|------|----------|
| **Correctness** | 答案内容是否正确 | 与 gold answer 对比（人工/LLM评判） |
| **Completeness** | 答案是否覆盖了问题的所有方面 | 检查所有 sub-questions 是否都被回答 |
| **Faithfulness** | 答案是否忠实于检索到的证据 | 答案中的每个声明是否都有证据支撑 |
| **Citation Accuracy** | 引用是否正确 | 引用的规则号是否真的支持对应声明 |
| **Hallucination Rate** | 答案中无证据支持的内容比例 | 无证据声明数 / 总声明数 |

### 2.3 路由与规划指标

| 指标 | 定义 |
|------|------|
| **Route Accuracy** | Planner 分类 (direct/multi_hop) 是否正确 |
| **Intent Accuracy** | 7 类 intent 分类是否正确 |
| **Decomposition Quality** | 子任务拆分是否合理（人工评判） |
| **Tool Selection Accuracy** | 该用 tool 时是否用了，不该用时是否没用 |
| **Retrieval Strategy Match** | 选择的检索策略是否最适合该查询 |

### 2.4 系统级指标

| 指标 | 定义 |
|------|------|
| **End-to-End Latency** | 从收到请求到返回响应的总时间 |
| **LLM Token Usage** | 每次查询消耗的 token 数 |
| **Fallback Rate** | LLM 回退到启发式的比例 |
| **Second Retrieval Rate** | 需要第二轮检索的比例 |

---

## 3. 评估原理

### 3.1 RAG 评估的核心思想

RAG 系统的评估不同于普通 QA 系统，因为它的答案 **必须基于检索到的证据**。这带来一个关键区分：

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│  普通 QA 评估:                                         │
│  问题 + 标准答案 → 对比 → 得分                         │
│                                                        │
│  RAG 评估 (更复杂):                                    │
│                                                        │
│  问题 ──┐                                              │
│         ├─→ 检索结果 ──→ 检索质量评估                   │
│         │                                              │
│         ├─→ 生成答案 ──→ 答案正确性评估                 │
│         │                                              │
│         └─→ (答案, 检索结果) ──→ 忠实度评估             │
│                                                        │
│  三者缺一不可！                                         │
│  检索好但答案差 = 推理问题                              │
│  答案好但检索差 = 可能是幻觉                            │
│  答案好检索也好但不忠实 = 答案没用到证据                │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 3.2 评估中的 "Ground Truth" 概念

评估需要有参照标准（ground truth）。在本项目中：

```
┌─────────────────────────────────────────────────────────────┐
│              Ground Truth 的三个层次                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  GT-1: 检索层面的 ground truth                               │
│  "这个问题应该检索到哪些 chunks？"                           │
│  → 人工标注每个问题对应的 relevant_chunk_ids                  │
│  → 例: "Rule 14A.35是什么" → [chunk_14A_35, chunk_14A_def]  │
│                                                             │
│  GT-2: 答案层面的 ground truth                               │
│  "这个问题的正确答案是什么？"                                │
│  → 人工编写 gold standard answer                             │
│  → 不需要完美措辞，但需要包含正确的关键信息点                │
│                                                             │
│  GT-3: 引用层面的 ground truth                               │
│  "答案应该引用哪些规则？"                                    │
│  → 人工标注 expected_citations (规则编号列表)                 │
│  → 例: ["Rule 14A.35", "Rule 14A.36", "Chapter 14A定义"]    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 自动评估 vs 人工评估

| 方法 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **精确匹配** | Route 分类、规则编号 | 完全客观 | 只适用于有明确正确答案的指标 |
| **Token 重叠** | 答案文本对比 | 简单快速 | 不理解语义 |
| **LLM-as-Judge** | 答案质量、忠实度 | 接近人类判断 | 有成本、可能不稳定 |
| **人工评估** | 最终质量验证 | 最可靠 | 慢、贵、主观 |

**本项目推荐策略：**

```
• Route/Intent 分类 → 精确匹配 (自动)
• 检索召回率 → chunk_id 集合匹配 (自动)
• 答案正确性 → LLM-as-Judge + 少量人工验证
• 引用准确性 → 规则编号集合匹配 (自动)
• 忠实度 → LLM-as-Judge
```

### 3.4 RAGAS 评估框架原理

RAGAS (Retrieval Augmented Generation Assessment) 是目前最流行的 RAG 评估框架，它定义了几个核心指标：

```
┌─────────────────────────────────────────────────────────────┐
│                    RAGAS 核心指标                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Faithfulness (忠实度)                                    │
│     "答案中的每个声明是否都能从 context 中找到证据？"         │
│                                                             │
│     计算方法:                                                │
│     ① LLM 从答案中提取所有声明 (claims)                      │
│     ② 对每个 claim，LLM 判断 context 中是否有支持            │
│     ③ faithfulness = supported_claims / total_claims         │
│                                                             │
│  2. Answer Relevance (答案相关性)                             │
│     "答案是否真的在回答这个问题？"                            │
│                                                             │
│     计算方法:                                                │
│     ① LLM 从答案反向生成可能的问题                           │
│     ② 计算生成问题与原始问题的语义相似度                     │
│     ③ relevance = avg(similarity scores)                    │
│                                                             │
│  3. Context Precision (上下文精确度)                          │
│     "检索到的 context 中有多少是真正有用的？"                │
│                                                             │
│  4. Context Recall (上下文召回率)                             │
│     "正确答案所需的信息是否都在 context 中？"                │
│                                                             │
│     计算方法 (需要 ground truth answer):                     │
│     ① LLM 把 ground truth 拆成多个声明                       │
│     ② 检查每个声明是否能从 retrieved context 中推出           │
│     ③ recall = attributable_statements / total_statements   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**RAGAS 的局限性（对于本项目）：**

- RAGAS 的 Context Recall 需要 ground truth answer，制作成本高
- RAGAS 的 Faithfulness 使用通用 LLM 判断，可能不理解法律文本细微差别
- 本项目还需要 **法律特定指标**（规则编号匹配、交叉引用覆盖等），RAGAS 不直接支持

---

## 4. 数据集如何定义

### 4.1 数据集的结构定义

每条评估数据应包含以下字段：

```json
{
  "id": "eval_001",
  "query": "What are the disclosure requirements for a major transaction under the Main Board Listing Rules?",
  "query_zh": "主板上市规则中，重大交易的披露要求是什么？",
  
  "metadata": {
    "query_type": "direct",
    "intent": "obligation_summary",
    "difficulty": "medium",
    "requires_tool": false,
    "category": "disclosure",
    "chapters_involved": ["Chapter 14"],
    "language": "en"
  },
  
  "ground_truth": {
    "answer_key_points": [
      "Must publish announcement",
      "Must send circular to shareholders",
      "Must obtain shareholder approval at general meeting",
      "Thresholds: any ratio 25% or more but less than 100%"
    ],
    "expected_citations": [
      "Rule 14.34",
      "Rule 14.38",
      "Rule 14.40"
    ],
    "relevant_chunk_ids": [
      "main_board_ch14_rule_14_34",
      "main_board_ch14_rule_14_38",
      "main_board_ch14_rule_14_40",
      "main_board_ch14_definitions"
    ],
    "gold_answer": "Under the Main Board Listing Rules, a major transaction (where any size test ratio is 25% or more but less than 100%) requires the issuer to: (1) publish an announcement per Rule 14.34; (2) send a circular to shareholders per Rule 14.38; and (3) obtain shareholder approval at a general meeting per Rule 14.40.",
    "unacceptable_answers": [
      "Only requires an announcement (incomplete)",
      "Threshold is 50% (wrong threshold for major transaction)"
    ]
  },

  "evaluation_config": {
    "retrieval_k": 10,
    "min_recall": 0.8,
    "min_faithfulness": 0.9
  }
}
```

### 4.2 查询类型分布

一个好的评估数据集应覆盖系统的所有能力：

```
┌───────────────────────────────────────────────────────────┐
│          建议的数据集分布 (30-50 条)                        │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  By Query Type:                                           │
│  ├── direct (60%): 15-30 条                               │
│  │   ├── rule_lookup: 5-8 条  "Rule 14.34是什么?"         │
│  │   ├── obligation_summary: 5-8 条  "什么义务?"          │
│  │   ├── eligibility_check: 3-5 条  "是否需要?"           │
│  │   └── procedure_flow: 2-4 条  "步骤是什么?"            │
│  │                                                        │
│  └── multi_hop (40%): 10-20 条                            │
│      ├── comparison: 5-8 条  "A和B有什么区别?"            │
│      ├── cross_reference: 3-5 条  "A引用B哪些规则?"       │
│      └── calculation_required: 2-4 条  "如何计算?"         │
│                                                           │
│  By Difficulty:                                           │
│  ├── easy (30%): 单一规则, 直接查找                       │
│  ├── medium (50%): 需要 2-3 个规则, 一些推理              │
│  └── hard (20%): 需要多章交叉, 隐含关系                   │
│                                                           │
│  By Language:                                             │
│  ├── English (60%)                                        │
│  └── Chinese (40%)                                        │
│                                                           │
│  By Topic:                                                │
│  ├── Connected Transactions (30%)                         │
│  ├── Notifiable Transactions (30%)                        │
│  ├── Size Tests (20%)                                     │
│  └── Disclosure & Reporting (20%)                         │
│                                                           │
│  By Tool Requirement:                                     │
│  ├── No tool needed (70%)                                 │
│  └── Tool needed (30%): size test calculator, etc.        │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 4.3 难度等级定义

| 难度 | 定义 | 示例 |
|------|------|------|
| **Easy** | 单一规则查找，答案在一个 chunk 中 | "What is Rule 14A.35?" |
| **Medium** | 需要 2-3 个 chunks，可能需要简单推理 | "Connected transaction 的披露时间要求是什么?" |
| **Hard** | 需要多章节交叉引用，隐含条件推理 | "一家公司拟收购一项资产，交易对价为公司市值的30%，该资产由公司董事持有。这需要满足哪些规则？" |

---

## 5. 数据集如何获取和制作

### 5.1 数据来源

```
┌─────────────────────────────────────────────────────────────┐
│                 数据集来源策略                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  来源 1: 从 HKEX 文档中手动构造 (最可靠)                    │
│  ────────────────────────────────────────                    │
│  方法: 阅读规则文档 → 基于规则内容设计问题 → 标注正确答案    │
│  优点: Ground truth 绝对可靠                                 │
│  缺点: 耗时，需要法律知识                                    │
│  适合: 核心评估集 (20-30 条高质量)                           │
│                                                             │
│  来源 2: 从现有 test cases 提取和扩展                        │
│  ────────────────────────────────────────                    │
│  方法: 从 tests/ 中的测试数据提取有代表性的查询              │
│  优点: 已经有部分标注                                        │
│  缺点: 测试数据可能过于简单或过于技术化                      │
│  适合: 补充组件级评估数据                                    │
│                                                             │
│  来源 3: LLM 辅助生成 + 人工验证 (高效)                     │
│  ────────────────────────────────────────                    │
│  方法:                                                      │
│    ① 给 LLM 规则文本 → 让它生成合规类问题                    │
│    ② 人工审核问题质量和相关性                                │
│    ③ 人工标注正确答案和引用                                  │
│  优点: 快速获得大量候选问题                                  │
│  缺点: 答案仍需人工验证                                      │
│  适合: 扩大数据集规模 (30→50 条)                            │
│                                                             │
│  来源 4: 真实用户查询 (最有价值但目前没有)                   │
│  ────────────────────────────────────────                    │
│  方法: 收集实际合规人员的提问                                │
│  暂时不适用，但可作为 Phase 3 目标                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 制作步骤 (推荐流程)

```
Step 1: 确定覆盖范围
─────────────────────
• 列出系统已索引的规则章节 (Chapter 14, 14A, etc.)
• 为每个章节确定 2-3 个核心概念
• 目标: 确保每个核心概念至少有一个评估问题

Step 2: 编写查询 (Query Authoring)
──────────────────────────────────
• 为每个概念编写不同难度/类型的问题
• 同时提供中英文版本
• 确保 query_type 和 intent 分类的多样性

Step 3: 确定正确答案 (Ground Truth Labeling)
─────────────────────────────────────────────
• 打开对应的规则文档
• 找到回答该问题所需的所有规则条款
• 记录:
  - answer_key_points (关键信息点列表)
  - expected_citations (应引用的规则号)
  - relevant_chunk_ids (应检索到的 chunk IDs)
  - gold_answer (一段参考答案)

Step 4: 交叉验证
───────────────
• 让另一个人(或 LLM)独立回答同一问题
• 对比答案是否一致
• 若不一致，讨论后确定最终 ground truth

Step 5: 质量审核
───────────────
• 检查问题是否清晰无歧义
• 检查 ground truth 是否完整准确
• 检查 chunk_ids 是否存在于实际索引中
• 检查难度标注是否合理
```

### 5.3 具体制作示例

以下是一个制作评估数据的完整示例过程：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

示例: 为 "Connected Transaction" 制作一条评估数据

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: 选择规则条款
→ 打开 Main Board Listing Rules Chapter 14A
→ 选择 Rule 14A.31 (De minimis transactions exempt from reporting)

Step 2: 设计问题
→ English: "Under what conditions is a connected transaction 
   exempt from the reporting, announcement, and independent 
   shareholders' approval requirements?"
→ Chinese: "在什么条件下关连交易可以豁免报告、公告和独立
   股东批准的要求？"
→ query_type: direct
→ intent: eligibility_check
→ difficulty: medium

Step 3: 找到正确答案
→ 阅读 Rule 14A.31:
  "A connected transaction ... is exempt from the reporting, 
   announcement, circular and independent shareholders' approval 
   requirements if each of the percentage ratios is less than 
   0.1%..."
→ 也需要看 Rule 14A.33 (Revenue nature thresholds)
→ 综合得出 key points:
  1. Each percentage ratio < 0.1% (de minimis)
  2. Or: on normal commercial terms, in ordinary course, 
     and each ratio < 5% (for revenue nature)
  3. Various other exemptions in 14A.31-14A.34

Step 4: 标注 ground truth
→ answer_key_points: [上述3点]
→ expected_citations: ["Rule 14A.31", "Rule 14A.33"]
→ relevant_chunk_ids: [查找索引中对应的 chunk IDs]
→ gold_answer: [写一段完整回答]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 5.4 chunk_id 标注方法

标注 `relevant_chunk_ids` 是最费时的步骤。推荐方法：

```python
# 方法 1: 通过系统检索辅助标注
# 先运行系统获取检索结果，人工判断哪些是相关的

import json
from app.retrieval.hybrid_retriever import HybridRetriever

retriever = HybridRetriever()
results = retriever.retrieve("connected transaction exemption", top_k=20)

# 人工审查这 20 个结果，标记哪些是真正相关的
for r in results:
    print(f"[{r.chunk_id}] Score: {r.score:.3f}")
    print(f"  Rule: {r.chunk.rule_number}")
    print(f"  Text: {r.chunk.text[:100]}...")
    print(f"  Relevant? (y/n)")  # 人工判断
```

```python
# 方法 2: 通过规则编号直接定位
# 如果你知道正确答案应引用 Rule 14A.31，直接找包含该规则的 chunks

from app.retrieval.index_store import IndexStore

store = IndexStore()
chunks = store.get_chunks_by_rule_number("14A.31")
# → 直接获得对应 chunk_ids
```

---

## 6. 评估流程设计

### 6.1 自动评估 Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                  Evaluation Pipeline                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────────┐    │
│  │Benchmark │     │  System      │     │   Evaluator      │    │
│  │ Dataset  │────▶│  Under Test  │────▶│   (Metrics)      │    │
│  │(JSON)    │     │  (API call)  │     │                  │    │
│  └──────────┘     └──────────────┘     └────────┬─────────┘    │
│                                                  │              │
│                                                  ▼              │
│                                        ┌──────────────────┐    │
│                                        │  Evaluation      │    │
│                                        │  Report          │    │
│                                        │  (JSON + CSV)    │    │
│                                        └──────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 评估代码架构建议

```
evaluation/
├── __init__.py
├── benchmark/
│   ├── dataset_v1.json          # 评估数据集
│   ├── dataset_schema.json      # JSON Schema 定义
│   └── README.md                # 数据集说明
├── metrics/
│   ├── __init__.py
│   ├── retrieval_metrics.py     # Recall@K, Precision@K, MRR
│   ├── answer_metrics.py        # Correctness, Completeness
│   ├── faithfulness_metrics.py  # Faithfulness, Citation Accuracy
│   └── routing_metrics.py       # Route/Intent accuracy
├── evaluator.py                 # 主评估器
├── llm_judge.py                 # LLM-as-Judge 实现
├── run_evaluation.py            # 评估运行脚本
└── reports/
    └── .gitkeep                 # 评估报告输出目录
```

### 6.3 评估运行流程

```python
# 伪代码: 评估流程
def run_evaluation(dataset_path, api_url):
    dataset = load_dataset(dataset_path)
    results = []
    
    for item in dataset:
        # 1. 调用系统
        response = call_api(api_url, item["query"])
        
        # 2. 计算检索指标
        retrieval_scores = compute_retrieval_metrics(
            retrieved_ids=extract_chunk_ids(response["retrieved_chunks"]),
            relevant_ids=item["ground_truth"]["relevant_chunk_ids"],
            k=10
        )
        
        # 3. 计算路由指标
        routing_scores = compute_routing_metrics(
            actual_type=response["query_type"],
            expected_type=item["metadata"]["query_type"],
            actual_intent=response.get("planner_output", {}).get("intent"),
            expected_intent=item["metadata"]["intent"]
        )
        
        # 4. 计算引用指标
        citation_scores = compute_citation_metrics(
            actual_citations=extract_rule_numbers(response["citations"]),
            expected_citations=item["ground_truth"]["expected_citations"]
        )
        
        # 5. 计算答案质量 (LLM-as-Judge)
        answer_scores = compute_answer_quality(
            question=item["query"],
            answer=response["answer"],
            gold_answer=item["ground_truth"]["gold_answer"],
            key_points=item["ground_truth"]["answer_key_points"],
            context=response["retrieved_chunks"]
        )
        
        results.append({
            "id": item["id"],
            "retrieval": retrieval_scores,
            "routing": routing_scores,
            "citation": citation_scores,
            "answer": answer_scores
        })
    
    # 6. 生成报告
    report = generate_report(results)
    return report
```

### 6.4 评估报告格式

```
═══════════════════════════════════════════════════════════════
              HKEX RAG Evaluation Report
              Date: 2026-04-30
              Dataset: benchmark_v1 (30 queries)
              System: Agentic RAG Workflow
═══════════════════════════════════════════════════════════════

Overall Scores:
┌─────────────────────────────┬───────┐
│ Metric                      │ Score │
├─────────────────────────────┼───────┤
│ Retrieval Recall@10         │ 0.78  │
│ Retrieval Precision@10      │ 0.45  │
│ Route Accuracy              │ 0.90  │
│ Intent Accuracy             │ 0.83  │
│ Citation Accuracy           │ 0.72  │
│ Answer Correctness          │ 0.75  │
│ Answer Completeness         │ 0.68  │
│ Faithfulness                │ 0.88  │
│ Hallucination Rate          │ 0.12  │
└─────────────────────────────┴───────┘

By Query Type:
┌──────────┬──────────┬────────────┬──────────────┐
│ Type     │ Count    │ Recall@10  │ Correctness  │
├──────────┼──────────┼────────────┼──────────────┤
│ direct   │ 18       │ 0.85       │ 0.82         │
│ multi_hop│ 12       │ 0.67       │ 0.64         │
└──────────┴──────────┴────────────┴──────────────┘

Error Analysis:
┌────────────────────────────────┬───────┐
│ Error Type                     │ Count │
├────────────────────────────────┼───────┤
│ Missing relevant rule          │ 4     │
│ Wrong rule retrieved           │ 2     │
│ Correct retrieval, weak answer │ 3     │
│ Hallucinated information       │ 2     │
│ Incomplete answer              │ 5     │
│ Tool should have been used     │ 1     │
└────────────────────────────────┴───────┘
```

---

## 7. 与 RAGAS 的关系

### 7.1 是否应该用 RAGAS？

```
┌─────────────────────────────────────────────────────────────┐
│           RAGAS vs 自定义评估 决策矩阵                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用 RAGAS 的场景:                                            │
│  ✓ 快速获得行业标准指标 (Faithfulness, Relevance)            │
│  ✓ 需要与其他 RAG 系统对比                                   │
│  ✓ 论文中需要引用标准评估方法                                │
│                                                             │
│  需要自定义的场景 (本项目的独特需求):                         │
│  ✓ Rule number 精确匹配 — RAGAS 不支持                      │
│  ✓ Cross-reference coverage — RAGAS 不支持                  │
│  ✓ 路由分类准确率 — 不属于 RAGAS 范畴                       │
│  ✓ Tool 调用正确性 — RAGAS 不支持                           │
│  ✓ 中英文双语评估 — RAGAS 需要额外配置                      │
│                                                             │
│  推荐: 两者结合                                              │
│  • 用 RAGAS 计算: Faithfulness, Context Recall              │
│  • 自定义计算: Route Accuracy, Rule Coverage,               │
│    Citation Accuracy, Tool Accuracy                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 RAGAS 集成方式

```python
# 安装: pip install ragas

from ragas import evaluate
from ragas.metrics import faithfulness, context_recall, context_precision
from datasets import Dataset

# 准备 RAGAS 格式数据
ragas_data = {
    "question": [...],       # 评估问题
    "answer": [...],         # 系统生成的答案
    "contexts": [...],       # 检索到的 contexts (List[List[str]])
    "ground_truth": [...],   # 标准答案
}

dataset = Dataset.from_dict(ragas_data)
result = evaluate(dataset, metrics=[faithfulness, context_recall, context_precision])
```

---

## 8. 实施路线图

### 8.1 分阶段推荐

```
Phase A: 最小可行评估 (1-2 天)
═══════════════════════════════════════
目标: 能跑通评估流程，有基础数据
├── 制作 15 条评估数据 (5 easy + 7 medium + 3 hard)
├── 实现 Route Accuracy 指标 (精确匹配)
├── 实现 Retrieval Recall@10 指标
├── 实现 Citation Accuracy 指标 (规则号匹配)
└── 生成简单文本报告

Phase B: 答案质量评估 (2-3 天)
═══════════════════════════════════════
目标: 评估答案本身的质量
├── 扩展到 30 条评估数据
├── 实现 LLM-as-Judge (Correctness, Completeness)
├── 实现 Faithfulness 指标
├── 添加错误分类 (error taxonomy)
└── 生成结构化报告

Phase C: 对比实验 (1-2 天)
═══════════════════════════════════════
目标: 证明系统的价值
├── Agentic RAG workflow vs naive 单轮检索 对比
├── 有 tool vs 无 tool 对比
├── 有 coverage loop vs 无 loop 对比
├── 生成对比图表
└── 可选: 集成 RAGAS

Phase D: 完善与自动化 (持续)
═══════════════════════════════════════
├── 扩展数据集到 50+ 条
├── CI 中自动运行评估
├── 建立 baseline 记录
└── 每次代码修改后回归测试
```

### 8.2 立即可做的第一步

如果你现在就想开始，建议从这里开始：

```bash
# 1. 创建评估目录结构
mkdir -p evaluation/benchmark evaluation/metrics evaluation/reports

# 2. 创建第一批评估数据 (从现有 demo queries 扩展)
# 编辑 evaluation/benchmark/dataset_v1.json

# 3. 写一个最简评估脚本
# evaluation/run_evaluation.py
```

**第一批 5 条评估数据可以来自：**
1. 现有的 4 条 demo queries → 补充 ground truth
2. 新增 1 条 tool-related query

这样你就有了一个可以运行的最小评估循环，后续只需不断扩充数据集和指标。

---

## 总结

| 问题 | 回答 |
|------|------|
| **评估目标** | 量化系统质量、定位瓶颈、驱动优化、支撑论文 |
| **核心指标** | Retrieval Recall, Faithfulness, Citation Accuracy, Route Accuracy |
| **评估原理** | 需要 Ground Truth (检索层+答案层+引用层)；自动+LLM-Judge+人工结合 |
| **数据集定义** | 每条: query + metadata + ground_truth (key_points, citations, chunk_ids, gold_answer) |
| **数据集获取** | 手动从规则构造 (核心) + LLM辅助生成 (扩展) + 从测试提取 (补充) |
| **推荐规模** | 先 15 条快速验证 → 扩展到 30 条 → 最终 50+ 条 |
| **与 RAGAS** | 结合使用: RAGAS 做标准指标, 自定义做法律领域特定指标 |
