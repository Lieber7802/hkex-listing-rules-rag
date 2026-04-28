# Phase 2 Agentic RAG 优化设计规范

> **基于：** `optimization.md` 和 `optimization-zh.md` 的分析结果  
> **目标：** 将 Phase 1 的最小可行原型升级为更强的、证据驱动的、工具增强的 Agentic RAG 系统

---

## 1. 执行摘要

Phase 1 成功交付了一个可运行的 Agentic RAG 后端原型，但其 agentic 能力仍然偏薄，更接近"带路由的混合检索 RAG"而非真正的"规划-检索-验证-执行"架构。

Phase 2 的核心目标是：

1. **强化规划能力**：从简单分类升级为执行控制器
2. **证据驱动迭代**：让检索循环基于缺失证据而非固定标志
3. **证据验证机制**：在答案生成前后加入覆盖度检查与支持验证
4. **工具集成**：引入 HKEX 专用工具（size test calculator、规则查找等）
5. **评估体系**：建立轻量评估框架指导后续优化

Phase 2 分为三个递进阶段：

- **Stage 1（优先级 A）**：强化现有 graph 的真实 agentic 能力
- **Stage 2（优先级 B）**：加入 HKEX 专用工具与领域能力
- **Stage 3（优先级 C）**：加入评估、记忆与可观测性

---

## 2. Phase 1 现状回顾

### 2.1 已实现的能力

- ✅ 文档导入与结构感知分块
- ✅ 混合检索（BM25 + FAISS）
- ✅ LangGraph StateGraph 工作流
- ✅ Planner：`direct` vs `multi_hop` 分类
- ✅ 可选二次检索
- ✅ 基于证据的答案生成
- ✅ 引用格式化
- ✅ FastAPI 接口

### 2.2 确认的薄弱点

**Planner 层面：**
- 只有两类标签（`direct` / `multi_hop`）
- 子查询拆分基于正则匹配
- 无真正的执行计划对象
- 无工具调用决策

**检索层面：**
- 二次检索不是证据驱动，而是固定标志触发
- 无 query rewriting
- 无证据覆盖度评估
- 多跳检索只是简单合并，无依赖建模

**推理层面：**
- 无论断到引用的对齐验证
- 无子任务覆盖度检查
- 无矛盾检测
- 置信度估计偏弱

**系统层面：**
- 无工具使用能力
- 无对话记忆
- 无会话状态管理
- 无评估框架

---

## 3. Phase 2 设计原则

### 3.1 核心原则

1. **证据优先**：所有决策基于证据充分性，而非固定规则
2. **可追溯性**：每个中间步骤可检查、可解释
3. **领域适配**：针对 HKEX 合规场景的特定需求优化
4. **渐进增强**：保持系统简洁，避免过度工程化
5. **评估驱动**：用小型 benchmark 指导优化方向

### 3.2 不做的事情

Phase 2 明确**不包含**：

- ❌ 大型多 agent 自主系统
- ❌ 复杂的自我反思循环
- ❌ 生产级部署与监控
- ❌ Web 前端（可选，非必需）
- ❌ 完整的 RAGAS 评估平台

---

## 4. Stage 1 设计：强化 Agentic Graph

### 4.1 目标

让现有 LangGraph 工作流从"结构上 agentic"变为"行为上 agentic"。

### 4.2 升级 Planner 为执行控制器

**当前状态：**
```python
class PlannerOutput:
    query_type: str  # "direct" or "multi_hop"
    sub_queries: List[str]
    needs_second_retrieval: bool
    reason: str
```

**升级后：**
```python
class ExecutionPlan:
    intent: str  # 更细粒度的意图分类
    sub_tasks: List[SubTask]
    retrieval_strategy: str
    requires_tool: bool
    tool_name: Optional[str]
    evidence_requirements: Dict[str, str]
    answer_format: str
    confidence_threshold: float
```

**新增意图类别：**
- `rule_lookup`：查找特定规则
- `obligation_summary`：总结披露义务
- `comparison`：比较多个规则
- `eligibility_check`：资格/阈值判断
- `procedure_flow`：程序流程说明
- `calculation_required`：需要计算
- `multi_condition`：多条件综合判断

**实现方式：**
- 保留启发式规则作为 baseline
- 可选：加入轻量 LLM 分类器
- 输出结构化执行计划对象

### 4.3 证据覆盖度检查节点

**新增节点：** `EvidenceCoverageChecker`

**职责：**
1. 评估第一轮检索结果
2. 对每个 sub_task 检查是否有强支撑 chunk
3. 识别缺失信息
4. 决定是否需要定向二次检索

**输出：**
```python
class CoverageAssessment:
    sub_task_coverage: Dict[str, bool]
    missing_information: List[str]
    coverage_score: float
    needs_targeted_retrieval: bool
    retrieval_targets: List[str]
```

### 4.4 定向二次检索

**当前问题：**
- 二次检索只是重跑原始 query
- 无针对性

**升级方案：**
1. 基于 `CoverageAssessment.retrieval_targets` 生成新查询
2. 可选：对模糊查询进行 query rewriting
3. 只检索未覆盖的子任务
4. 记录检索轮次与原因

**新增 state 字段：**
```python
retrieval_rounds: List[RetrievalRound]
query_rewrites: List[QueryRewrite]
```

### 4.5 证据选择与重排节点

**新增节点：** `EvidenceSelector`

**职责：**
1. 去重高度重叠的 chunks
2. 优先选择带明确 rule_number 的 chunks
3. 保证证据多样性（避免单一章节垄断）
4. 按子任务相关性分组

**输出：**
```python
class SelectedEvidence:
    chunks_by_subtask: Dict[str, List[Chunk]]
    diversity_score: float
    rule_coverage: List[str]
```

### 4.6 答案验证节点

**新增节点：** `AnswerVerifier`

**职责：**
1. 检查答案中的每个主要论断
2. 验证是否有对应的 chunk 支撑
3. 检测跨 chunk 的矛盾
4. 评估置信度

**输出：**
```python
class VerificationResult:
    claim_support_map: Dict[str, List[str]]  # claim -> chunk_ids
    unsupported_claims: List[str]
    contradictions: List[Contradiction]
    confidence_level: str  # "high" / "medium" / "low"
    revision_needed: bool
```

### 4.7 更新后的 LangGraph 工作流

```
┌─────────────────┐
│  Enhanced       │
│  Planner        │──▶ ExecutionPlan
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  First          │
│  Retrieval      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Coverage       │──▶ CoverageAssessment
│  Checker        │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 Sufficient  Insufficient
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │  Targeted       │
    │    │  Retrieval      │
    │    └────────┬────────┘
    │             │
    └─────────────┘
         │
         ▼
┌─────────────────┐
│  Evidence       │
│  Selector       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Reasoning      │
│  Agent          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Answer         │
│  Verifier       │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 Verified  Needs Revision
    │         │
    │         └──▶ (回到 Reasoning 或降级置信度)
    │
    ▼
┌─────────────────┐
│  Citation       │
│  Formatter      │
└────────┬────────┘
         │
         ▼
       END
```

### 4.8 Stage 1 预期成果

- Planner 输出结构化执行计划
- 检索迭代由证据缺失驱动
- 答案生成前有证据选择
- 答案生成后有验证机制
- 系统仍保持轻量，但行为更 agentic

---

## 5. Stage 2 设计：HKEX 专用工具集成

### 5.1 目标

让系统能处理纯检索无法高质量解决的 HKEX 合规任务。

### 5.2 工具接口设计

**扩展现有 `BaseTool`：**
```python
class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def run(self, inputs: Dict[str, Any]) -> ToolResult:
        pass
    
    @abstractmethod
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        pass
```

### 5.3 优先工具列表

#### 5.3.1 SizeTestCalculatorTool

**功能：**
- 计算资产比率、收益比率、代价比率、股本比率、收入比率
- 判断交易类型（须予公布、主要、非常重大）

**输入：**
```python
{
    "transaction_value": float,
    "company_assets": float,
    "company_revenue": float,
    "company_market_cap": float,
    "consideration": float
}
```

**输出：**
```python
{
    "ratios": {
        "assets_ratio": float,
        "profits_ratio": float,
        "revenue_ratio": float,
        "consideration_ratio": float,
        "equity_capital_ratio": float
    },
    "classification": str,  # "discloseable" / "major" / "very_substantial"
    "applicable_rules": List[str],
    "disclosure_requirements": List[str]
}
```

#### 5.3.2 RuleLookupTool

**功能：**
- 按 rule number 精确查找
- 返回完整条款文本与元数据

**输入：**
```python
{
    "rule_number": str,  # e.g., "14A.35"
    "include_related": bool
}
```

**输出：**
```python
{
    "rule_text": str,
    "chapter": str,
    "section_title": str,
    "related_rules": List[str],
    "source_path": str
}
```

#### 5.3.3 DisclosureChecklistTool

**功能：**
- 根据交易类型生成披露清单
- 列出所有必需披露项

**输入：**
```python
{
    "transaction_type": str,
    "is_connected": bool,
    "size_classification": str
}
```

**输出：**
```python
{
    "checklist_items": List[ChecklistItem],
    "deadlines": Dict[str, str],
    "applicable_rules": List[str]
}
```

#### 5.3.4 TransactionClassifierTool

**功能：**
- 基于结构化输入判断交易性质
- 识别是否为关联交易

**输入：**
```python
{
    "counterparty": str,
    "relationship": str,
    "transaction_nature": str
}
```

**输出：**
```python
{
    "is_connected": bool,
    "connection_type": str,
    "applicable_chapter": str,
    "exemptions": List[str]
}
```

### 5.4 工具路由逻辑

**在 ExecutionPlan 中加入：**
```python
requires_tool: bool
tool_name: Optional[str]
tool_inputs: Optional[Dict[str, Any]]
```

**Planner 决策规则：**
- 查询包含"计算"、"比率"、"size test" → `SizeTestCalculatorTool`
- 查询明确提到 rule number → `RuleLookupTool`
- 查询要求"清单"、"步骤"、"需要披露什么" → `DisclosureChecklistTool`
- 查询涉及"关联方"、"connected person" → `TransactionClassifierTool`

### 5.5 工具与检索融合

**新增节点：** `ToolExecutor`

**工作流分支：**
```
Planner
  │
  ├─ requires_tool = False ──▶ Retrieval Path
  │
  └─ requires_tool = True
       │
       ├─ tool_only ──▶ ToolExecutor ──▶ Reasoning
       │
       └─ tool_plus_retrieval ──▶ Parallel:
                                    ├─ ToolExecutor
                                    └─ Retrieval
                                    │
                                    └─▶ Reasoning (融合两者)
```

### 5.6 Stage 2 预期成果

- 系统能处理需要计算的合规问题
- 系统能生成结构化清单输出
- 答案融合检索证据与工具输出
- 工具调用可追溯、可验证

---

## 6. Stage 3 设计：评估、记忆与可观测性

### 6.1 轻量评估框架

**目标：**
- 建立小型 benchmark（20-30 个标注问题）
- 跟踪关键指标
- 指导后续优化

**评估维度：**
1. **检索质量**
   - Recall@k
   - 关键规则是否被检索到
   
2. **引用质量**
   - 引用是否相关
   - 引用是否充分支撑答案
   
3. **答案质量**
   - 答案是否正确
   - 答案是否完整
   - 是否有无支撑的论断
   
4. **工具使用**
   - 该用工具时是否用了
   - 工具输出是否正确

**失败分类：**
- `wrong_rule_retrieved`：检索到错误条款
- `missing_rule`：漏检关键条款
- `weak_synthesis`：条款正确但综合回答弱
- `unsupported_claim`：过度自信的无支撑回答
- `tool_not_used`：应该用工具但没用
- `tool_misused`：不该用工具但用了

**实现：**
```python
# data/evaluation/benchmark.json
{
    "questions": [
        {
            "id": "q001",
            "query": "...",
            "query_type": "direct",
            "expected_rules": ["14A.35", "14A.36"],
            "expected_tool": null,
            "gold_answer": "...",
            "evaluation_notes": "..."
        }
    ]
}
```

### 6.2 对话记忆

**目标：**
- 支持多轮对话
- 维护会话上下文

**设计：**
```python
class ConversationMemory:
    session_id: str
    messages: List[Message]
    case_context: Optional[CaseContext]
    
class CaseContext:
    transaction_type: Optional[str]
    is_connected: Optional[bool]
    size_ratios: Optional[Dict[str, float]]
    discussed_rules: List[str]
    pending_questions: List[str]
```

**API 升级：**
```python
# POST /chat
{
    "query": str,
    "session_id": Optional[str],  # 新增
    "case_context": Optional[Dict]  # 新增
}
```

### 6.3 增强 API 输出

**新增响应字段：**
```python
class ChatResponse:
    # 原有字段
    query_type: str
    answer: str
    citations: List[Citation]
    retrieved_chunks: List[dict]
    uncertainty_note: Optional[str]
    planner_output: Optional[PlannerOutput]
    
    # 新增字段
    execution_trace: ExecutionTrace  # 新增
    retrieval_rounds: List[RetrievalRound]  # 新增
    selected_evidence: SelectedEvidence  # 新增
    coverage_assessment: CoverageAssessment  # 新增
    confidence_level: str  # 新增
    tool_calls: List[ToolCall]  # 新增
    verification_result: VerificationResult  # 新增
```

### 6.4 Stage 3 预期成果

- 有小型 benchmark 指导优化
- 支持多轮对话与案件上下文
- API 输出足够丰富，便于调试与前端开发
- 系统质量可量化评估

### 6.5 Stage 3 专项重构：LLM 主导的 Planner 与完整任务拆解

#### 6.5.1 设计目标

当前 Planner 已从纯粹的 `direct / multi_hop` 分类器升级为轻量执行控制器，但其核心能力仍以启发式规则为主，任务拆解也仍停留在字符串级别切分。若系统要进入更强的 Agentic RAG 阶段，就需要把 Planner 重构为：

- **LLM 主导路由**：由 LLM 负责主要路由判断
- **启发式兜底**：当 LLM 超时、返回格式不合法、或结果缺失时回退到规则
- **启发式校验**：当 LLM 输出与明确规则信号明显冲突时，发出告警或触发降级
- **条件拆解**：仅在复杂问题上执行任务拆解，避免简单问题被过度处理
- **完整拆解**：将复杂问题拆成结构化、可执行、带依赖关系的子任务，而不是简单字符串切分

本次重构的目标不是让 Planner 变成一个大而全的黑盒节点，而是将其拆解为边界清晰、易于验证的两个节点：

1. **RoutePlanner**：决定“怎么处理这个问题”
2. **TaskDecomposer**：决定“这个复杂问题需要拆成哪些任务”

#### 6.5.2 架构决策：拆成两个节点，而不是一个节点

本设计明确采用**双节点解耦方案**，不采用单节点同时承担路由和拆解的设计。

**不推荐单节点方案的原因：**

- 路由错误与拆解错误难以区分，调试成本高
- 简单问题也会被迫走拆解流程，增加延迟和噪音
- 评估体系难以定位问题究竟出在路由判断还是拆解质量
- 后续接入工具调用、会话记忆、失败重试时边界不清晰

**采用双节点方案的原因：**

- 路由与拆解是两个不同决策层级，职责天然不同
- 简单查询可直接跳过拆解，减少 LLM 调用与复杂度
- 便于为每一层分别做 fallback、校验、日志、评估
- 更适合后续引入工具规划与多轮上下文

因此，Planner 重构后的结构为：

```text
User Query
  -> LLMRoutePlanner
  -> HeuristicRouteValidator
  -> Conditional Branch
       -> direct/simple path: Retriever
       -> complex path: TaskDecomposer
  -> Retrieval / Tool Execution
  -> Reasoning
  -> Answer Verification
```

#### 6.5.3 节点一：LLMRoutePlanner

`LLMRoutePlanner` 是新的主路由节点，负责输出高层执行决策，而不是直接做低层任务拆解。

**输入：**

- 用户原始 query
- 可选：当前会话上下文 `session_context`
- 可选：已识别结构化案件上下文 `case_context`

**输出：**

```python
class RouteDecision(BaseModel):
    query_type: str  # direct / multi_hop
    intent: str
    requires_decomposition: bool
    retrieval_strategy: str  # single_pass / multi_query / targeted_iterative
    requires_tool: bool
    tool_name: Optional[str]
    tool_inputs_hint: Dict[str, Any]
    answer_format: str
    route_reason: str
    llm_confidence: float
    validation_warnings: List[str]
    fallback_used: bool
```

**该节点负责的判断：**

- 当前问题是简单查询还是复杂查询
- 是否需要任务拆解
- 检索应走单次、并行、多轮还是定向迭代
- 是否应该调用工具
- 如果需要工具，优先建议哪个工具
- 最终答案更适合什么组织方式

**不由该节点负责：**

- 子任务列表的详细生成
- 子任务之间的依赖建模
- 具体工具输入值的完整填充

也就是说，`LLMRoutePlanner` 只回答“怎么走流程”，不回答“拆成哪些原子任务”。

#### 6.5.4 先判断是否需要拆解

本设计明确要求：**必须先判断是否需要任务拆解，再决定是否进入 TaskDecomposer。**

这是该方案的一个硬约束。

**简单问题的典型特征：**

- 查询目标单一
- 只涉及一类规则或一项义务
- 不需要比较、条件组合、例外分析、步骤整合
- 不需要多阶段证据组合

例如：

- `What is Rule 14A.35?`
- `What are the disclosure requirements for connected transactions?`
- `What is the announcement deadline?`

这类问题应输出：

- `query_type = direct`
- `requires_decomposition = false`
- `retrieval_strategy = single_pass`

然后直接进入检索链路，不走拆解节点。

**复杂问题的典型特征：**

- 涉及比较
- 涉及条件组合
- 涉及多个规则域或多个义务域
- 涉及工具调用与规则解释的混合流程
- 涉及先检索、再判断、再合并的多阶段过程

例如：

- `Compare the disclosure requirements for connected and notifiable transactions`
- `If a transaction involves a connected person and exceeds the size test threshold, what obligations apply?`
- `What rules apply, what disclosures are required, and whether shareholder approval is needed?`

这类问题应输出：

- `query_type = multi_hop`
- `requires_decomposition = true`
- `retrieval_strategy = targeted_iterative` 或 `multi_query`

然后才进入 `TaskDecomposer`。

#### 6.5.5 节点二：TaskDecomposer

`TaskDecomposer` 是新的低层任务规划节点，仅在 `requires_decomposition = true` 时触发。

其职责不是重新判断路由，而是在既定路由决策下，把复杂问题拆成结构化、可执行的任务图。

**输入：**

- 原始 query
- `RouteDecision`
- 可选：上下文、会话状态、案件上下文

**输出：**

```python
class SubTask(BaseModel):
    id: str
    type: str  # retrieval / tool / reasoning_prep
    goal: str
    query: str
    depends_on: List[str]
    priority: str  # high / medium / low
    expected_output: str


class DecompositionPlan(BaseModel):
    subtasks: List[SubTask]
    merge_strategy: str
    coverage_targets: List[str]
    decomposition_reason: str
    llm_confidence: float
    validation_warnings: List[str]
    fallback_used: bool
```

**拆解要求：**

- 子任务必须是完整语义单元，不能是字符串残句
- 子任务必须有明确目标，而不只是一个碎片化查询片段
- 子任务之间必须显式声明依赖关系
- 可并行执行的任务应在 `depends_on = []` 或无交叉依赖下显式体现
- 若问题需要比较，必须至少有两个核心信息收集任务与一个合并比较任务
- 若问题需要工具与规则解释混合，则工具任务与检索任务应显式分开

#### 6.5.6 LLM 为主，启发式作为 fallback 与校验

本设计中，启发式规则不再负责主决策。它只承担两项职责：

1. **Fallback**
2. **Validation**

##### A. Fallback

以下情况触发启发式回退：

- LLM 超时
- LLM 返回空结果
- LLM 返回 JSON 格式非法
- LLM 输出缺失关键字段
- LLM 输出字段值超出允许枚举范围

此时回退到现有 `PlannerAgent` 的启发式逻辑，确保系统最差情况下仍可用。

##### B. Validation

当 LLM 成功返回结果后，不直接盲信，而是用规则做一致性校验。

**路由层校验规则：**

- query 出现明确 `Rule 14A.35` 且无比较/条件词时，不应判为 `comparison`
- query 含 `compare / difference / versus / vs`，不应输出 `single_pass`
- query 含 `size test / ratio / percentage / calculate`，不应漏掉 `requires_tool = true`
- query 含多个明显并列目标时，不应把 `requires_decomposition` 设为 `false`

**拆解层校验规则：**

- `multi_hop` 问题不能被拆成只有一个子任务
- 子任务不能是残句，如只剩 `Rule 14A.36?`
- 依赖图不能有环
- 比较型问题应至少存在两个平行信息收集任务
- 工具型任务必须有清晰的工具目标与预期输出

校验后的处理策略如下：

- 若只是轻微冲突：保留 LLM 输出，并追加 `validation_warnings`
- 若存在重大冲突：
  - 优先尝试 LLM 重试一次，附带规则告警作为约束
  - 若仍冲突，则降级为启发式 fallback

#### 6.5.7 推荐的 Prompt 策略

为了降低 LLM 输出漂移，本设计建议采用**结构化 JSON 输出 + 固定枚举值 + 低温度**策略。

**RoutePlanner Prompt 要求：**

- 只输出 JSON
- 所有字段必须填写
- `query_type`、`retrieval_strategy`、`answer_format` 必须从给定枚举值中选
- 明确要求优先判断“是否需要拆解”
- 明确要求简单问题不要过度拆解

**TaskDecomposer Prompt 要求：**

- 只输出 JSON
- 每个子任务必须完整、独立、可执行
- 必须带 `depends_on`
- 必须描述最终 `merge_strategy`
- 若问题并不复杂，不得强行拆解

#### 6.5.8 工具选择纳入路由设计

你已明确要求将工具选择 schema 一并纳入本次设计，因此本设计把工具决策放在 `RoutePlanner` 层完成，而不是放到拆解节点后临时决定。

**原因：**

- 工具需求本质上是高层路由决策的一部分
- 工具名称应先于任务拆解被确定，才能决定是否需要 `tool` 类型子任务
- 若工具是主路径之一，拆解节点应在此基础上生成 `tool` 子任务，而不是反过来推测是否需要工具

**推荐 schema：**

```python
class ToolDecision(BaseModel):
    requires_tool: bool
    tool_name: Optional[str]
    tool_mode: str  # none / tool_only / tool_plus_retrieval
    tool_inputs_hint: Dict[str, Any]
    tool_reason: str
```

其中：

- `tool_name` 是推荐工具名，如 `size_test_calculator`, `rule_lookup`, `transaction_classifier`
- `tool_mode` 表示路由方式：
  - `none`
  - `tool_only`
  - `tool_plus_retrieval`
- `tool_inputs_hint` 是提示性的输入结构，不要求此时全部填满

#### 6.5.9 新的工作流建议

重构后的 Planner 相关工作流如下：

```text
User Query
  -> LLMRoutePlanner
  -> HeuristicRouteValidator
  -> Route Conflict Handler
      -> ok: continue
      -> retry once with constraints
      -> fallback to heuristic planner
  -> Conditional Branch
      -> requires_decomposition = false
           -> Retriever / ToolExecutor / CoverageChecker
      -> requires_decomposition = true
           -> TaskDecomposer
           -> DecompositionValidator
           -> Task Graph Execution
  -> EvidenceSelector
  -> Reasoning
  -> AnswerVerifier
```

这里的关键变化是：

- 简单问题直接绕过拆解节点
- 复杂问题才进入 `TaskDecomposer`
- 路由失败和拆解失败的处理逻辑分开
- 工具选择在路由阶段已经被纳入

#### 6.5.10 对现有代码的改造建议

当前代码中已有的 `PlannerAgent` 不建议直接删除，而应拆分成三个用途：

1. **HeuristicRouteFallback**
2. **HeuristicRouteValidator**
3. **Legacy compatibility planner**（仅在迁移期保留）

建议新增组件：

- `app/agents/llm_route_planner.py`
- `app/agents/route_validator.py`
- `app/agents/task_decomposer.py`
- `app/agents/decomposition_validator.py`
- `app/schemas/planning.py`

建议新增 schema：

- `RouteDecision`
- `ToolDecision`
- `SubTask`
- `DecompositionPlan`
- `RouteValidationResult`
- `DecompositionValidationResult`

#### 6.5.11 验收标准

本专项重构完成时，应满足以下条件：

- 简单 query 可直接跳过任务拆解
- 复杂 query 会进入任务拆解节点
- 路由层以 LLM 为主判断
- 启发式只承担 fallback 与校验职责
- 路由层输出包含工具决策信息
- 拆解层输出完整、可执行、带依赖的子任务列表
- 存在路由冲突处理机制
- 至少一组 benchmark 用于评估：
  - 路由准确率
  - 拆解完整性
  - fallback 触发率
  - 规则冲突率

#### 6.5.12 设计结论

这次 Planner 重构不应被理解为“把启发式换成 LLM”这么简单，而应理解为：

- 将原本混在一起的“路由”和“拆解”彻底分层
- 让 LLM 负责主判断
- 让规则负责最低保障与一致性校验
- 让简单问题保持简单
- 让复杂问题真正进入结构化任务规划

最终结果应是：系统从“基于规则的轻量 Planner”升级为“LLM 主导、规则校验、条件拆解、支持工具路由”的完整规划子系统。

---

## 7. 技术栈更新

### 7.1 保持不变

- Python 3.10+
- FastAPI
- Pydantic
- LangGraph
- FAISS
- BM25
- DeepSeek Reasoner
- Ollama + BGE-M3

### 7.2 新增依赖

- `pytest-benchmark`：性能测试
- `jsonschema`：工具输入验证
- `redis`（可选）：会话存储
- `prometheus-client`（可选）：指标导出

---

## 8. 实现约束

### 8.1 保持简洁

- 每个新节点职责单一
- 避免过度抽象
- 优先可读性而非通用性

### 8.2 向后兼容

- Phase 1 的 API 端点保持可用
- 新字段为可选
- 旧的 demo queries 仍能运行

### 8.3 渐进交付

- Stage 1 完成后即可独立验证
- Stage 2 不依赖 Stage 3
- 每个 Stage 都是可交付的增量

---

## 9. 验收标准

### 9.1 Stage 1 完成标准

- [ ] Planner 输出 `ExecutionPlan` 对象
- [ ] 存在 `EvidenceCoverageChecker` 节点
- [ ] 二次检索基于 `CoverageAssessment` 触发
- [ ] 存在 `EvidenceSelector` 节点
- [ ] 存在 `AnswerVerifier` 节点
- [ ] 至少一个 demo query 展示完整 trace
- [ ] 答案包含 `confidence_level` 字段

### 9.2 Stage 2 完成标准

- [ ] 至少实现 2 个工具（建议：SizeTestCalculator + RuleLookup）
- [ ] Planner 能决策 `requires_tool`
- [ ] 存在 `ToolExecutor` 节点
- [ ] 至少一个 demo query 调用工具
- [ ] 工具输出与检索证据能融合

### 9.3 Stage 3 完成标准

- [ ] 存在 benchmark.json 文件（至少 10 个问题）
- [ ] 能运行评估脚本并输出指标
- [ ] API 支持 `session_id` 参数
- [ ] 响应包含 `execution_trace`
- [ ] 至少一个多轮对话 demo

---

## 10. 风险与缓解

### 10.1 风险：复杂度失控

**缓解：**
- 严格按 Stage 递进
- 每个 Stage 独立验收
- 避免提前优化

### 10.2 风险：工具输出不可靠

**缓解：**
- 工具输出附带置信度
- 工具调用可回退到纯检索
- 工具输入验证严格

### 10.3 风险：评估成本过高

**缓解：**
- 只做轻量 benchmark
- 不追求完整 RAGAS
- 人工标注控制在 20-30 题

---

## 11. 后续扩展方向（Phase 3+）

Phase 2 完成后，可考虑：

- Web 前端
- 更多工具（财务分析、文档生成）
- 更强的 query understanding（NER、意图识别）
- 生产级部署
- 完整评估平台

但这些不在当前 Phase 2 范围内。

---

## 12. 总结

Phase 2 将 Phase 1 的"带路由的 RAG"升级为"规划-检索-验证-执行"的真正 Agentic 系统。

核心改进：
1. **Planner** → **执行控制器**
2. **固定检索** → **证据驱动迭代**
3. **直接推理** → **证据选择 + 验证**
4. **纯检索** → **检索 + 工具融合**
5. **无评估** → **轻量 benchmark**

预期结果：系统从 demo 原型走向可用的合规助手。
