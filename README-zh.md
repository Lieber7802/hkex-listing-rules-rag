# HKEX 上市规则合规 Agentic RAG 系统

一个面向香港交易所（HKEX）上市规则合规问答的全栈智能检索增强生成（Agentic RAG）系统。主要功能：

- **React 聊天前端** — 支持实时 SSE 流式输出
- **多轮对话** — 会话管理 + 上下文感知的查询改写
- **混合检索** — BM25 + 稠密向量嵌入，倒数排名融合（RRF）
- **双工作流** — V1（启发式规划器）和 V2（LLM 路由 + 验证）
- **工具链执行** — 规模测试计算器、交易分类器、披露清单、规则查询
- **带引用来源的答案** — 证据验证与矛盾检测
- **中英双语支持** — 规划器、覆盖检查器、验证器均可处理中文

## 项目结构

```
project_root/
├── app/
│   ├── api/                    # FastAPI 端点
│   │   ├── chat.py                  # V1 API（根路径）
│   │   ├── chat_v2.py              # V2 API（/v2 前缀）
│   │   └── chat_v2_stream.py      # V2 SSE 流式端点
│   ├── agents/                 # LangGraph 工作流与 Agent 节点
│   │   ├── graph_state.py               # LangGraph 状态定义
│   │   ├── langgraph_workflow.py        # V1 StateGraph 编排
│   │   ├── langgraph_workflow_v2.py     # V2 LLM 路由编排
│   │   ├── streaming_workflow.py        # SSE 流式包装器
│   │   ├── llm_route_planner.py         # LLM 路由规划（V2）
│   │   ├── route_validator.py           # 启发式路由验证（V2）
│   │   ├── task_decomposer.py           # 多跳查询分解（V2）
│   │   ├── decomposition_validator.py   # 分解验证（V2）
│   │   ├── planner_agent.py             # 启发式查询分类
│   │   ├── reasoning_agent.py           # 答案生成（LLM + 回退）
│   │   ├── contextual_query_rewriter.py # 多轮对话上下文改写
│   │   ├── query_rewriter.py            # 二次检索定向改写
│   │   ├── coverage_checker.py          # 证据覆盖评估
│   │   ├── evidence_selector.py         # 证据去重与排序
│   │   ├── answer_verifier.py           # 声明验证
│   │   └── citation_formatter.py        # 引用格式化
│   ├── core/                   # 配置与日志
│   ├── ingestion/              # 文档加载、清洗、分块
│   ├── models/                 # 数据模型
│   │   └── conversation.py          # ConversationSession, ConversationTurn
│   ├── retrieval/              # 嵌入、BM25、混合检索
│   ├── schemas/                # Pydantic 请求/响应模型
│   │   ├── query.py                 # QueryRequest, PlannerOutput
│   │   ├── response.py             # ChatResponse, HealthResponse
│   │   ├── planning.py             # RouteDecision, DecompositionPlan (V2)
│   │   ├── tool.py                  # ToolCall, ToolResult
│   │   ├── citation.py             # 引用模型
│   │   └── document.py             # 文档/分块模型
│   ├── services/               # 业务逻辑服务
│   │   ├── session_store.py         # 线程安全的会话持久化（JSONL）
│   │   └── history_formatter.py     # 对话历史格式化（供 LLM 使用）
│   ├── tools/                  # HKEX 合规工具
│   │   ├── base_tool.py             # BaseTool 抽象基类 + ToolRegistry
│   │   ├── size_test_calculator.py  # 5 项 HKEX 规模测试比率计算
│   │   ├── transaction_classifier.py # 根据比率进行交易分类
│   │   ├── disclosure_checklist.py  # 按分类等级生成披露清单
│   │   ├── rule_lookup.py           # 精确规则文本查询
│   │   └── tool_chain.py           # 自动链：size_test → classifier → checklist
│   └── main.py                 # FastAPI 应用 + 前端静态文件服务
├── frontend/                   # React 聊天界面
│   ├── src/
│   │   ├── components/              # UI 组件（Header, InputBar, Messages 等）
│   │   ├── hooks/                   # useChat Hook（SSE 流式）
│   │   ├── services/                # API 客户端
│   │   └── types/                   # TypeScript 类型定义
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/
│   ├── raw/                    # 源文档
│   ├── processed/              # 清洗后文档
│   ├── chunks/                 # 分块数据
│   ├── indexes/                # FAISS + BM25 索引
│   └── sessions/               # JSONL 会话文件（已 gitignore）
├── scripts/                    # 命令行脚本（ingest, build_index, demo）
├── tests/                      # 单元与集成测试（30+ 文件）
├── docs/                       # 文档
└── requirements.txt
```

## 环境配置

### 前置条件

- Python 3.10+
- Node.js 18+（用于前端）
- pip

### 后端安装

```bash
pip install -r requirements.txt
```

### 前端安装

```bash
cd frontend
npm install
npm run build    # 生产构建（由 FastAPI 提供服务）
```

前端开发模式（热重载）：
```bash
cd frontend
npm run dev      # 在 5173 端口启动 Vite 开发服务器
```

### 配置说明

通过环境变量管理（在项目根目录创建 `.env` 文件）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `deepseek` | LLM 提供商 |
| `LLM_MODEL` | `deepseek-reasoner` | LLM 模型名称 |
| `LLM_API_KEY` | — | LLM API 密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | LLM API 基础 URL |
| `EMBEDDING_PROVIDER` | `ollama` | 嵌入提供商（ollama 或 sentence-transformers） |
| `EMBEDDING_MODEL` | `bge-m3` | 嵌入模型名称 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API 基础 URL |
| `SESSION_TTL_MINUTES` | `60` | 会话过期时间（分钟） |
| `SESSION_MAX_TURNS` | `50` | 每个会话最大轮次 |
| `SESSION_HISTORY_WINDOW` | `5` | 注入 LLM 上下文的最近问答对数量 |

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

将 HKEX 上市规则文档放入 `data/raw/` 目录。支持的格式：
- `.txt` - 纯文本
- `.md` - Markdown
- `.pdf` - PDF（通过 PyMuPDF）

### 2. 导入文档

```bash
python scripts/ingest_documents.py
```

### 3. 构建索引

```bash
python scripts/build_index.py
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload
```

服务将在 http://localhost:8000 提供。
- API 文档：http://localhost:8000/docs
- 聊天界面：http://localhost:8000（需要先构建 `frontend/dist/`）

### 5. 查询 API

使用 curl：
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "关联交易的披露要求是什么？"}'
```

多轮对话：
```bash
# 第一轮（创建新会话）
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "规则 14A.35 是什么？"}'

# 后续轮次（传入上一次响应中的 conversation_id）
curl -X POST "http://localhost:8000/v2/chat" \
  -H "Content-Type: application/json" \
  -d '{"query": "那豁免条件呢？", "conversation_id": "<上一次响应中的id>"}'
```

### 6. 运行示例查询

```bash
python scripts/demo_queries.py
```

## API 端点

### V1 端点（根路径）

| 端点 | 说明 |
|------|------|
| `GET /health` | 服务健康检查 |
| `POST /chat` | 使用 V1 工作流查询（启发式规划器） |

### V2 端点（`/v2` 前缀）

| 端点 | 说明 |
|------|------|
| `GET /v2/health` | V2 服务健康检查 |
| `POST /v2/chat` | 使用 V2 工作流查询（LLM 路由，支持多轮） |
| `POST /v2/chat/stream` | SSE 流式响应，包含中间事件 |
| `GET /v2/chat/stream?query=...` | 兼容 EventSource 的流式端点 |

### 请求格式

```json
{
  "query": "关联交易的披露要求是什么？",
  "conversation_id": "可选的会话ID"
}
```

如果不传 `conversation_id`，系统将创建新会话。在后续请求中传入该 ID 即可继续对话。

### 响应格式

```json
{
  "query_type": "direct",
  "answer": "...",
  "citations": [...],
  "retrieved_chunks": [...],
  "uncertainty_note": null,
  "planner_output": {...},
  "coverage_assessment": {...},
  "verification_result": {...},
  "confidence_level": "high",
  "conversation_id": "uuid-会话ID",
  "turn_number": 1,
  "route_decision": {...},
  "decomposition_plan": {...},
  "tool_calls": [...],
  "tool_results": [...]
}
```

### SSE 事件类型

使用流式端点时，工作流各阶段会发送以下事件：

| 事件 | 数据 | 说明 |
|------|------|------|
| `routing_complete` | `{query_type, route_summary}` | 查询路由完成 |
| `tool_executed` | `{tool_name, success, output_preview}` | 工具执行完成 |
| `retrieval_complete` | `{num_chunks, top_score}` | 检索完成 |
| `reasoning_started` | `{}` | LLM 推理开始 |
| `answer_chunk` | `{content}` | 答案文本（流式） |
| `done` | `{total_time_ms, tools_executed}` | 工作流完成 |

## 系统架构

### V1 工作流（启发式）

```
用户查询
  -> PlannerAgent（正则分类）
  -> HybridRetriever（BM25 + 稠密向量融合，RRF）
  -> [可选：二次检索（覆盖不足时）]
  -> CoverageChecker
  -> EvidenceSelector
  -> ReasoningAgent
  -> AnswerVerifier
  -> CitationFormatter
  -> ChatResponse
```

### V2 工作流（LLM 路由）

```
用户查询 + 对话历史
  -> ContextualQueryRewriter（多轮上下文注入）
  -> LLM Route Planner（意图、分解、工具决策）
  -> Route Validator（启发式交叉验证）
  -> [冲突时重试 / 回退到启发式]
  -> Task Decomposer（多跳查询分解）
  -> Decomposition Validator
  -> [Tool Executor（计算类查询）]
  -> Hybrid Retriever
  -> Coverage Checker -> [可选二次检索]
  -> Evidence Selector
  -> Reasoning Agent（带对话上下文）
  -> Answer Verifier
  -> 响应（含 conversation_id + turn_number）
```

### 多轮对话

系统跨轮次维护对话状态：

1. **SessionStore**：线程安全的内存缓存 + JSONL 文件持久化。会话在可配置 TTL 后自动过期。
2. **ContextualQueryRewriter**：将后续查询（如"那豁免条件呢？"）改写为自包含查询，利用对话历史补全上下文。
3. **历史注入**：最近的问答对被注入推理 Agent 的上下文中，确保多轮答案连贯。

### 工具链

当检测到计算类查询时，工具按顺序执行：
1. `size_test_calculator` — 计算 5 项 HKEX 规模测试比率
2. `transaction_classifier` — 根据比率映射交易分类 + 适用规则
3. `disclosure_checklist` — 按分类等级生成所需披露项目
4. `rule_lookup` — 从索引中精确查找规则文本

## 前端

React 前端提供聊天界面，支持：

- 实时 SSE 流式输出（Token 逐字显示）
- 多轮对话与会话持久化
- 证据面板展示检索到的分块与引用
- 工作流阶段进度指示器
- Tailwind CSS 响应式设计

### 技术栈

- React 18 + TypeScript
- Vite（构建工具）
- Tailwind CSS（样式）
- Server-Sent Events（流式通信）

## 运行测试

```bash
# 运行所有测试
pytest -v

# 运行单个测试文件
pytest tests/test_planner.py -v

# 运行单个测试用例
pytest tests/test_planner.py::TestPlannerAgent::test_classify_direct_simple_lookup -v
```

测试无需 LLM 或索引依赖（均已 Mock）。

## 技术栈

- **后端框架**：FastAPI, Pydantic, pydantic-settings
- **Agent 编排**：LangGraph (StateGraph 工作流)
- **LLM**：DeepSeek Reasoner（通过 OpenAI 兼容 API）
- **嵌入模型**：BGE-M3 通过 Ollama 本地部署
- **向量存储**：FAISS
- **词法检索**：BM25（自定义实现 + RRF 融合）
- **前端**：React 18, Vite, Tailwind CSS, TypeScript
- **测试框架**：pytest, httpx

## 许可证

本项目为 CS6520 课程作业的教育目的而开发。
