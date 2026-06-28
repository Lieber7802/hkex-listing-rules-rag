# HKEX Listing Rules 合规 Agentic RAG 系统

默认文档语言：中文

English version: [README-en.md](README-en.md)

这是一个面向香港交易所（HKEX）上市规则合规问答的全栈 Agentic RAG 系统。系统使用 FastAPI + LangGraph 编排检索、证据筛选、工具计算和答案核验，支持英文和中文查询，并提供 React 前端和 SSE 流式输出。

## 当前状态

- 后端：FastAPI，提供 V1 和 V2 两套聊天接口。
- 前端：React + TypeScript + Vite，支持流式聊天和证据面板。
- 检索：BM25 + dense embedding 并行检索，RRF 融合排序。
- 向量化：Ollama 本地 embedding，支持断点续跑和批量 embedding。
- 知识库：支持 PDF、Markdown、文本文件；官方 HTML 页面已通过脚本转换为干净 Markdown 后 ingestion。
- 工具链：支持 size test、交易分类、披露清单、规则精确查询，并可自动串联。
- 测试：当前完整测试集为 399 个测试用例。

## 核心功能

- **合规问答**：基于 HKEX 上市规则、指引、决定、FAQ 和官方资料回答问题。
- **引用和证据**：答案包含可追溯 citations，并通过 evidence selector 和 verifier 降低幻觉风险。
- **混合检索**：BM25 与 dense embedding 并行执行，再通过 Reciprocal Rank Fusion 合并。
- **中文支持**：BM25、coverage checker 和 verifier 使用中英文混合 tokenization，适配 CJK 文本。
- **多轮对话**：基于 session store 保存对话历史，并把最近问答注入上下文。
- **计算工具**：支持交易规模测试、交易分类、披露要求清单和规则查询。
- **断点向量化**：embedding 结果按 chunk 缓存，中断后可继续，不会重算已完成内容。

## 项目结构

```text
app/
  api/                  FastAPI endpoints: /chat, /v2/chat, /v2/chat/stream
  agents/               LangGraph workflow, planner, retriever nodes, verifier
  core/                 config, logger, shared LLM client
  ingestion/            document loader, cleaner, structure-aware chunker
  retrieval/            Ollama embedder, BM25, hybrid retriever, index store
  schemas/              Pydantic request/response/document models
  services/             session persistence and history formatting
  tools/                size test, classifier, checklist, rule lookup
frontend/               React chat UI
scripts/                ingestion, index building, HKEX download/conversion tools
tests/                  unit and integration tests
data/
  raw/                  source documents and converted Markdown
  processed/            cleaned documents, ignored by git
  chunks/               chunk JSON files, ignored by git
  indexes/              FAISS, BM25 and embedding cache, ignored by git
```

## 环境要求

- Python 3.10+
- Node.js 18+
- Ollama，本地 embedding 需要
- DeepSeek 或其他 OpenAI-compatible LLM API key

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

安装和构建前端：

```bash
cd frontend
npm install
npm run build
```

开发模式前端：

```bash
cd frontend
npm run dev
```

## 配置

项目通过 `.env` 配置。关键变量如下：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | LLM provider |
| `LLM_MODEL` | `deepseek-v4-flash` | LLM 模型 |
| `LLM_API_KEY` | 空 | LLM API key |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible API base URL |
| `EMBEDDING_PROVIDER` | `ollama` | embedding provider |
| `EMBEDDING_MODEL` | `qwen3-embedding:4b` | Ollama embedding 模型 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama 服务地址 |
| `RETRIEVAL_TOP_K_BM25` | `20` | BM25 候选数量 |
| `RETRIEVAL_TOP_K_DENSE` | `20` | dense retrieval 候选数量 |
| `RETRIEVAL_TOP_K_FINAL` | `10` | RRF 后最终候选数量 |
| `RRF_K` | `20` | RRF 平滑常数 |

Ollama embedding 模型：

```bash
ollama pull qwen3-embedding:4b
```

## 知识库准备

### 1. 放入原始文件

把官方文档放入 `data/raw/`。当前 ingestion 直接支持：

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

HTML 不直接进入 ingestion。已下载的 HKEX HTML 应先转换为 Markdown：

```bash
python scripts/convert_hkex_html_to_markdown.py
```

转换输出位于：

```text
data/raw/html_converted/
```

转换审计和日志位于：

```text
data/raw/_download_manifests/
```

`DocumentLoader` 会跳过 `_download_manifests` 等内部目录，避免把下载清单或审计报告混入知识库。

### 2. Ingestion

```bash
python scripts/ingest_documents.py
```

该步骤会生成：

```text
data/processed/
data/chunks/
```

### 3. 建立索引

```bash
python scripts/build_index.py --embedding-workers 2 --embedding-batch-size 32 --progress-every 32
```

索引会生成到：

```text
data/indexes/
```

`data/processed/`、`data/chunks/`、`data/indexes/` 都已在 `.gitignore` 中忽略，不应提交到远程仓库。

### 断点续跑

向量化会把每个 chunk 的 embedding 缓存在：

```text
data/indexes/_embedding_cache/
```

查看当前进度：

```bash
python scripts/build_index.py --cache-status
```

如果构建中断，重新运行同一条 build 命令即可继续。缓存 key 包含 provider、model、chunk_id 和文本内容；如果 chunk 文本变化，会自动重新计算该 chunk。

## 启动服务

```bash
uvicorn app.main:app --reload
```

访问：

- Web UI: http://localhost:8000
- Swagger: http://localhost:8000/docs

如果没有构建前端，根路径会返回后端状态说明；运行 `cd frontend && npm run build` 后 FastAPI 会直接提供 React UI。

## API

| Endpoint | 说明 |
| --- | --- |
| `GET /health` | V1 健康检查 |
| `POST /chat` | V1 查询接口 |
| `GET /v2/health` | V2 健康检查 |
| `POST /v2/chat` | V2 查询接口，返回 route/tool/evidence 信息 |
| `POST /v2/chat/stream` | V2 SSE 流式接口 |
| `GET /v2/chat/stream?query=...` | EventSource 兼容流式接口 |

示例：

```bash
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the disclosure requirements for a major transaction?"}'
```

多轮对话：

```bash
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is Rule 14A.35?"}'

curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "What exemptions are available?", "conversation_id": "<conversation_id>"}'
```

## V2 工作流

当前生产主线为 `app/agents/langgraph_workflow_v2.py`：

```text
planner_agent_v2
  -> should_route
    -> execute_tool
      -> tool_input_extraction
      -> tool_executor
      -> tool_mode_router
        -> evidence_selector -> reasoning -> answer_verifier
        -> retriever -> coverage -> evidence_selector -> reasoning -> answer_verifier
    -> retriever
      -> coverage
      -> evidence_selector
      -> reasoning
      -> answer_verifier
```

V2 的关键点：

- 使用启发式 `PlannerAgent` 做 intent 和路由判断。
- LLM 只用于工具输入抽取和答案生成，不再依赖 LLM route planner。
- 工具输入抽取有三层恢复：LLM 抽取、regex fallback、执行前 recovery。
- `tool_only` 查询会跳过 coverage checker。
- `AgentState` 中 `retrieved_chunks`、`citations`、`retrieval_rounds`、`tool_calls`、`tool_results` 使用 LangGraph accumulation。
- 从 state 还原 retrieval results 时必须保留 `bm25_score` 和 `dense_score`，否则 coverage strategy 会失真。

## 工具链

当前核心 HKEX 计算工具：

1. `size_test_calculator`：计算 assets、profits、revenue、consideration、equity capital 五个 size test ratio。
2. `transaction_classifier`：根据 size test 结果分类交易，并处理 connected party override。
3. `disclosure_checklist`：根据分类生成披露、公告、通函、股东批准等清单。
4. `rule_lookup`：根据 rule number 精确返回规则文本。

自动链路：

```text
size_test -> classifier -> checklist
```

## 检索与索引

- BM25 使用预分词语料，中文采用字符 bigram。
- Dense embedding 默认使用 Ollama `qwen3-embedding:4b`。
- BM25 和 dense retrieval 并行执行。
- RRF 融合默认 `k=20`。
- 向量索引使用 FAISS `IndexFlatIP`，embedding 会做 L2 normalization。
- chunk id 在 chunker 中会保证唯一，避免向量检索按 ID 回查时命中错误 chunk。

## 前端

React 前端提供：

- SSE 流式聊天
- evidence panel
- tool call 和 tool result 展示
- conversation id 持续对话
- responsive layout

技术栈：

- React 18
- TypeScript
- Vite
- Tailwind CSS
- lucide-react

## 测试

运行完整测试：

```bash
pytest -v
```

运行单个测试文件：

```bash
pytest tests/test_planner_refactor.py -v
```

运行单个测试：

```bash
pytest tests/test_planner_refactor.py::TestPlannerAgent::test_classify_direct_simple_lookup -v
```

测试不依赖真实 LLM 或已有索引。

## 常用脚本

| 脚本 | 说明 |
| --- | --- |
| `scripts/ingest_documents.py` | raw -> processed/chunks |
| `scripts/build_index.py` | chunks -> FAISS/BM25 indexes，支持 embedding cache |
| `scripts/convert_hkex_html_to_markdown.py` | 官方 HTML 清洗转换为 Markdown |
| `scripts/build_hkex_p1_p2_manifest.py` | 生成 P1/P2 下载 manifest |
| `scripts/download_hkex_p1_p2_recommended.py` | 下载 P1/P2 推荐文件 |
| `scripts/download_hkex_archive_first_pass.py` | 下载 archive first-pass 文件 |
| `scripts/demo_queries.py` | 运行示例查询 |

## License

本项目用于 CityU CS6520 课程项目和研究演示。
