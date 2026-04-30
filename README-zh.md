# HKEX 上市规则合规 Agentic RAG 系统

第一阶段后端原型

## 项目概述

本项目实现了一个面向香港交易所（HKEX）上市规则合规问答的智能检索增强生成（Agentic RAG）系统。第一阶段交付了一个可本地运行、可测试的后端原型，具备以下功能：

- 文档导入与结构感知分块
- 混合检索（BM25 + 稠密向量嵌入）
- 基于 LangGraph 的 Agent 编排（规划器与推理节点）
- 带引用来源的答案生成
- FastAPI 接口

## 项目结构

```
project_root/
├── app/
│   ├── api/                # FastAPI 端点
│   ├── core/               # 配置与日志
│   ├── ingestion/          # 文档加载、清洗、分块
│   ├── retrieval/          # 嵌入、BM25、混合检索
│   ├── agents/             # LangGraph 工作流、规划器、推理
│   │   ├── graph_state.py      # LangGraph 状态定义
│   │   ├── langgraph_workflow.py # StateGraph 编排
│   │   ├── planner_agent.py    # 查询分类
│   │   ├── reasoning_agent.py  # 答案生成
│   │   └── citation_formatter.py # 引用格式化
│   ├── schemas/            # Pydantic 数据模型
│   ├── tools/              # 工具接口（第二阶段扩展）
│   └── main.py             # FastAPI 应用
├── data/
│   ├── raw/                # 源文档
│   ├── processed/          # 清洗后文档
│   ├── chunks/             # 分块数据
│   ├── indexes/            # 向量与 BM25 索引
│   └── demo/               # 示例查询
├── scripts/                # 命令行脚本
├── tests/                  # 单元测试
├── docs/                   # 文档
└── requirements.txt
```

## 环境配置

### 前置条件

- Python 3.10+
- pip

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置说明

配置通过环境变量管理：

- LLM_PROVIDER: LLM 提供商（默认：deepseek）
- LLM_MODEL: LLM 模型名称（默认：deepseek-reasoner）
- LLM_API_KEY: LLM API 密钥
- LLM_BASE_URL: LLM API 基础 URL（默认：https://api.deepseek.com）
- EMBEDDING_PROVIDER: 嵌入提供商，ollama 或 sentence-transformers（默认：ollama）
- EMBEDDING_MODEL: 嵌入模型名称（默认：bge-m3）
- OLLAMA_BASE_URL: Ollama API 基础 URL（默认：http://localhost:11434）

在项目根目录创建 .env 文件设置这些变量。

#### Ollama 配置（用于本地嵌入）

1. 安装 Ollama：https://ollama.ai
2. 拉取 BGE 模型：
```bash
ollama pull bge-m3
```
3. 启动 Ollama 服务（通常自动在 11434 端口运行）

#### DeepSeek 配置（用于 LLM）

1. 从 https://platform.deepseek.com 获取 API 密钥
2. 在 .env 文件中设置：
```
LLM_API_KEY=你的-api-密钥
```

## 使用方法

### 1. 准备文档

将 HKEX 上市规则文档放入 data/raw/ 目录。支持的格式：
- .txt - 纯文本
- .md - Markdown
- .pdf - PDF（基础支持，接口已预留扩展空间）

### 2. 导入文档

```bash
python scripts/ingest_documents.py
```

此命令将：
- 从 data/raw/ 加载文档
- 清洗并规范化文本
- 创建结构感知的分块
- 保存到 data/processed/ 和 data/chunks/

### 3. 构建索引

```bash
python scripts/build_index.py
```

此命令将：
- 从 data/chunks/ 加载分块数据
- 生成向量嵌入
- 构建 FAISS 向量索引
- 构建 BM25 词法索引
- 保存到 data/indexes/

### 4. 启动服务

```bash
uvicorn app.main:app --reload
```

API 将在 http://localhost:8000 提供服务。
API 文档：http://localhost:8000/docs

### 5. 查询 API

使用 curl：
```bash
curl -X POST "http://localhost:8000/chat" -H "Content-Type: application/json" -d "{\"query\": \"关联交易的披露要求是什么？\"}"
```

使用 Python：
```python
import httpx
response = httpx.post("http://localhost:8000/chat", json={"query": "规则 14A.35 是什么？"})
print(response.json())
```

### 6. 运行示例查询

```bash
python scripts/demo_queries.py
```

## API 端点

### GET /health

返回服务健康状态。

响应：
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### POST /chat

提交合规问题。

请求：
```json
{
  "query": "关联交易的披露要求是什么？"
}
```

响应：
```json
{
  "query_type": "direct",
  "answer": "...",
  "citations": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "rule_number": "14A.35",
      "section_title": "披露要求",
      "chapter": "第 14A 章",
      "source_path": "...",
      "snippet": "...",
      "score": 0.85
    }
  ],
  "retrieved_chunks": [...],
  "uncertainty_note": null,
  "planner_output": {
    "query_type": "direct",
    "sub_queries": [...],
    "needs_second_retrieval": false,
    "reason": "..."
  }
}
```

## 运行测试

```bash
pytest -v
```

## 第一阶段范围

第一阶段交付内容：
- 可本地运行的后端原型
- 文档导入流水线
- 结构感知分块
- 混合检索（BM25 + 稠密向量）
- 基于规划器的查询路由
- 带引用来源的答案
- FastAPI 接口

第一阶段明确不包含：
- Web 前端
- 规模测试计算器工具
- 基准测试数据集
- RAGAS 评估
- 生产环境部署

## 第二阶段扩展点

代码库已为后续扩展预留接口：

- 工具接口：app/tools/base_tool.py 提供添加工具的基类
- 评估接口：分块和响应数据模型支持评估框架
- 前端友好响应格式：API 响应结构化，可直接被前端消费
- LLM 提供商抽象：app/agents/reasoning_agent.py 支持多种 LLM 提供商

## LangGraph 工作流架构

系统使用 LangGraph StateGraph 实现 Agent 编排：

```
┌─────────┐    ┌───────────┐    ┌──────────────┐
│ Planner │───▶│ Retriever │───▶│   条件路由    │
└─────────┘    └───────────┘    └──────┬───────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              "retrieve_again"    "reason"           "end"
                    │                  │
                    ▼                  ▼
            ┌───────────────┐    ┌──────────┐
            │   二次检索     │    │  推理    │───▶ END
            └───────┬───────┘    └──────────┘
                    │
                    ▼
            ┌──────────┐
            │  推理    │───▶ END
            └──────────┘
```

### 工作流节点说明

| 节点 | 功能 |
|------|------|
| Planner | 查询分类（direct/multi_hop），生成子查询 |
| Retriever | 混合检索，返回相关分块 |
| Second Retrieval | 可选的二次检索（当证据不足时） |
| Reasoning | 基于证据生成答案，格式化引用 |

## 技术栈

- 后端框架：FastAPI, Pydantic
- Agent 编排：LangGraph (StateGraph 工作流)
- LLM：DeepSeek Reasoner（通过 OpenAI 兼容 API）
- 嵌入模型：BGE-M3 通过 Ollama 本地部署
- 向量存储：FAISS
- 词法检索：BM25（自定义实现）
- 测试框架：pytest, httpx

## 许可证

本项目为 CS6520 课程作业的教育目的而开发。
