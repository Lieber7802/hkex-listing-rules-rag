Project Name

Phase 1 Implementation of Agentic RAG for HKEX Listing Rules Compliance

1. 当前阶段目标

本阶段只实现项目的核心后端原型，用于支撑第一阶段研究报告。
目标是验证以下几点：

能够完成 HKEX 相关规则文档的收集、清洗、切分与索引构建
能够实现一个可运行的基础 Agentic RAG 流程
能够对用户的合规问答进行检索、初步任务分解、证据整合与带引用回答
为第二阶段预留前端、tool、benchmark、评测系统的扩展接口

本阶段不做以下内容：

不做前端页面
不做 Size Test Calculator 等专用 tool
不做 benchmark 数据集构建
不做完整评测系统
不做复杂多 agent 深度优化
不做生产级部署
2. 本阶段的交付物

请构建以下内容：

2.1 可运行的后端项目

一个可本地运行的 Python 后端工程，支持：

文档导入
文本切分
向量索引构建
混合检索
基础 agent orchestration
问答接口
引用返回
2.2 初始知识库处理流水线

支持将 HKEX Listing Rules 相关文档导入系统，并生成：

清洗后的文本
分块后的 chunk 数据
向量索引
检索元数据
2.3 基础 Agentic RAG 原型

至少包含以下能力：

query classification / routing
retrieval planning
evidence retrieval
answer synthesis with citations
2.4 开发文档

提供：

项目目录结构说明
环境安装说明
运行说明
API 调用示例
第二阶段扩展建议
3. 本阶段范围约束
3.1 文档范围

本阶段优先只处理以下与项目最相关的规则范围：

Notifiable Transactions
Connected Transactions
Size Tests 相关章节
相关 disclosure / reporting obligations（如有）

不要试图覆盖所有 HKEX 监管文档。
优先保证小范围内的质量与结构化效果。

3.2 问题类型范围

本阶段只需要支持以下两类问题：

Direct clause retrieval
用户问某类规则、某个义务、某个条款要求
Basic multi-hop compliance question
用户问题需要结合多个条款进行基础整合回答

本阶段先不强求复杂数值计算题，不实现专门 calculator。

4. 技术目标

本阶段请重点实现一个“最小可行 Agentic RAG”，而不是完整产品。
要求满足：

比普通单轮 RAG 多一个“任务拆分 / 路由”步骤
支持 citation-grounded answer
代码结构清晰，方便第二阶段扩展 tool、evaluation、frontend
5. 推荐系统架构
5.1 总体流程

实现如下主链路：

User Query
→ Planner / Router
→ Retriever
→ Evidence Selection / Reranking
→ Reasoning / Answer Generator
→ Final Response with Citations

6. 本阶段建议实现的模块
6.1 document_ingestion

职责：

读取本地文档（PDF / txt / md / html，如暂时不好处理 PDF，可先保留接口）
提取文本
保存原始文本与中间产物

要求：

代码结构清晰
后续方便替换为更强的 PDF parser
6.2 document_cleaning

职责：

去除无意义空白、页眉页脚、乱码
统一段落格式
尽量保留章节结构、条款编号、标题层级

要求：

不要把规则编号破坏掉
不要纯粹按 token 粗暴切块
6.3 chunking_service

职责：

基于法律/规则文档结构进行切分
优先按章节、section、rule number 进行层次化切分
对过长内容再做二次分块

每个 chunk 至少保存这些字段：

chunk_id
document_id
chapter
section_title
rule_number
text
source_path
page_number（如果能提取）
parent_section

要求：

重点体现 structure-aware chunking
保证 citation 时能追溯回来源
6.4 embedding_and_indexing

职责：

对 chunk 建立向量索引
同时保留 BM25 所需文本索引
支持 hybrid retrieval

建议：

使用一个简单稳定的 embedding 模型
向量库可选 FAISS 或 Chroma
BM25 可以单独实现或使用现成库
6.5 retrieval_service

职责：

接收 query
执行 hybrid retrieval：
lexical retrieval（BM25）
dense retrieval（embedding）
合并结果
返回 top-k 候选 chunk

可选增强：

简单 reranker
query rewriting

本阶段要求：

先做稳定版本
不追求复杂优化
6.6 planner_agent

职责：

对用户问题做基础任务判断
输出 query type
判断是否需要：
单轮检索
多条证据整合
二次检索

本阶段只需要支持分类：

direct
multi_hop

输出建议格式：

{
  "query_type": "direct",
  "sub_queries": ["..."],
  "needs_second_retrieval": false
}

要求：

逻辑尽量简单稳定
不需要复杂多 agent 自主决策
6.7 reasoning_agent

职责：

读取 planner 输出与 retrieval 结果
对多个证据进行整合
输出：
concise answer
supporting clauses
uncertainty note（如证据不足）

要求：

回答必须尽量引用检索到的内容
尽量避免无依据发挥
对不确定情况明确提示
6.8 citation_formatter

职责：

将被用到的 chunk 整理成可展示引用
返回格式中包含：
rule number
section title
source text snippet
source id / file path

本阶段引用格式不需要前端美化，但要结构化。

6.9 chat_api

职责：
提供一个最基础的 API，例如：

POST /chat

输入：

{
  "query": "What are the disclosure obligations for a connected transaction?"
}

输出：

{
  "query_type": "direct",
  "answer": "...",
  "citations": [
    {
      "rule_number": "...",
      "section_title": "...",
      "snippet": "...",
      "source_path": "..."
    }
  ],
  "retrieved_chunks": [...]
}

本阶段只需要 API，不需要前端。

7. 本阶段的 Agentic RAG 定义

请注意：本阶段实现的是基础版 Agentic RAG，不是复杂全功能版。

与 Native RAG 的区别要体现在：
有一个 planner/router 步骤
planner 可以做简单 task decomposition
retrieval 不是完全固定死的一次检索
answer synthesis 会基于多证据整合
但本阶段不需要：
大规模多 agent 通信
tool calling
memory system
self-reflection loop
benchmark 驱动优化
8. 本阶段不实现的内容

请明确不要在本阶段实现以下内容，除非只是预留接口：

8.1 前端
不做网页 UI
不做聊天界面
不做证据展示面板
8.2 专用 Tool
不实现 Size Test Calculator
不实现数值计算流程
只需为后续工具系统预留接口
8.3 Benchmark / Evaluation
不构建完整 benchmark 数据集
不实现 RAGAS
不实现自动化实验对比系统
8.4 高级工程化
不要求生产部署
不要求用户鉴权
不要求数据库持久化到复杂生产环境
不要求日志平台与监控平台
9. 为第二阶段预留的扩展接口

请在代码结构上为以下模块预留扩展点：

9.1 tool interface

未来将接入：

Size Test Calculator
结构化 financial input processing

建议预留接口：

class BaseTool:
    def name(self) -> str: ...
    def run(self, inputs: dict) -> dict: ...
9.2 evaluation interface

未来将接入：

benchmark loader
answer evaluator
retrieval evaluator
RAGAS / custom metrics
9.3 frontend-friendly response schema

当前 API 返回格式尽量结构化，以便第二阶段前端直接消费。

10. 推荐目录结构

建议使用类似如下结构：

project_root/
├── app/
│   ├── api/
│   │   └── chat.py
│   ├── core/
│   │   ├── config.py
│   │   └── logger.py
│   ├── ingestion/
│   │   ├── loader.py
│   │   ├── cleaner.py
│   │   └── chunker.py
│   ├── retrieval/
│   │   ├── embedder.py
│   │   ├── bm25.py
│   │   ├── hybrid_retriever.py
│   │   └── reranker.py
│   ├── agents/
│   │   ├── planner_agent.py
│   │   ├── reasoning_agent.py
│   │   └── orchestrator.py
│   ├── schemas/
│   │   ├── query.py
│   │   ├── response.py
│   │   └── citation.py
│   ├── tools/
│   │   └── base_tool.py
│   └── main.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── chunks/
│   └── indexes/
├── scripts/
│   ├── ingest_documents.py
│   ├── build_index.py
│   └── demo_queries.py
├── tests/
├── requirements.txt
└── README.md
11. 推荐技术栈
后端
Python
FastAPI
编排
可用 LangGraph / LangChain
如果觉得过重，也可以先自己写轻量 orchestrator
检索
BM25
embedding + vector store
FAISS 或 Chroma
LLM 接口
保持可配置，不绑定死单一 provider
使用统一封装，便于以后替换
12. 本阶段的实现原则
12.1 先求通，再求强

第一阶段目标是：

跑通 ingestion
跑通 retrieval
跑通 planner + answer synthesis
返回 citations

而不是追求最优精度。

12.2 优先保证可解释性

即使回答没那么华丽，也必须：

尽量给出依据
能定位到 chunk
能让后续 benchmark 使用
12.3 保证后续可扩展

代码需要支持第二阶段继续添加：

前端
tool
benchmark
evaluation
13. 本阶段建议的输出形式

请最终交付：

13.1 代码

一套可本地运行的后端代码

13.2 运行命令

例如：

文档导入命令
索引构建命令
服务启动命令
demo query 命令
13.3 示例结果

给出若干示例问答，展示：

query
answer
citations
retrieved chunks
13.4 README

README 至少包含：

项目简介
环境安装
配置方法
如何导入文档
如何构建索引
如何启动服务
如何测试 API
第二阶段待扩展模块说明
14. 给 OpenCode 的明确实现重点

请优先把时间放在下面这些点上，而不是 UI 或花哨功能：

文档结构保留与清洗
structure-aware chunking
hybrid retrieval
planner + reasoning 的基础编排
citation-grounded response
可维护的工程结构
15. 本阶段完成标准

如果满足以下条件，就算第一阶段达标：

能导入并处理 HKEX 相关规则文档
能构建 chunk 与索引
能接受用户问题并返回答案
答案能附带来源引用
系统具备一个基础 planner/router
代码结构支持第二阶段继续开发