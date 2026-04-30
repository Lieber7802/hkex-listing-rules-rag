# Planner 的真实职责分析

## 核心问题：Planner 是路由器还是任务拆解器？

### 答案：**两者都是，但侧重点不同**

---

## 一、Planner 的三层职责

### 第 1 层：问题分类与路由（主要职责）

这是 Planner 的**核心功能**，决定了后续的处理流程。

```python
# 示例：根据查询类型路由到不同的处理策略

query = "What is Rule 14A.35?"
# 路由决策：
# - query_type: "direct"
# - retrieval_strategy: "single_pass"
# - 路由到：单次检索 → 推理 → 答案

query = "Compare disclosure requirements for connected and notifiable transactions"
# 路由决策：
# - query_type: "multi_hop"
# - retrieval_strategy: "targeted_iterative"
# - 路由到：多次检索 → 证据选择 → 推理 → 答案
```

**路由的维度：**
- `query_type`: direct / multi_hop
- `retrieval_strategy`: single_pass / multi_query / targeted_iterative
- `requires_tool`: True / False
- `answer_format`: concise_with_citations / comparison_table / checklist_style

### 第 2 层：任务拆解（次要职责）

这是 Planner 的**辅助功能**，但拆解的粒度很粗。

```python
# 示例：任务拆解

query = "What are the disclosure requirements for Rule 14A.35 and Rule 14A.36?"

# 拆解结果：
sub_tasks = [
    "What are the disclosure requirements for Rule 14A.35?",
    "Rule 14A.36?"  # 注意：这里拆解不完整
]

# 问题：
# 1. 拆解是基于字符串分割（按 and/or），不是语义理解
# 2. 拆解后的子任务不一定是完整的、独立的
# 3. 拆解只是为了后续的多次检索，不是真正的任务分解
```

### 第 3 层：执行计划生成（新增职责）

这是 Stage 1 新增的功能，为后续节点提供执行指导。

```python
# 示例：执行计划

query = "Calculate the size test ratio for a connected transaction"

execution_plan = {
    "intent": "calculation_required",
    "sub_tasks": ["Calculate the size test ratio for a connected transaction"],
    "retrieval_strategy": "single_pass",
    "requires_tool": True,
    "tool_name": "SizeTestCalculator",
    "evidence_requirements": {
        "Calculate the size test ratio for a connected transaction": "high"
    },
    "answer_format": "concise_with_citations"
}

# 这个计划告诉后续节点：
# 1. 这是一个计算问题
# 2. 需要调用 SizeTestCalculator 工具
# 3. 同时需要检索相关规则作为背景
# 4. 答案应该包含引用
```

---

## 二、Planner vs 真正的任务拆解器

### 对比表

| 维度 | Planner（当前） | 真正的任务拆解器 |
|------|-----------------|-----------------|
| **职责** | 问题分类 + 路由 | 将复杂任务分解为原子操作 |
| **输入** | 用户查询 | 用户查询 + 上下文 |
| **输出** | 执行计划（高层） | 子任务列表（低层） |
| **拆解方式** | 字符串分割 | 语义理解 + 依赖分析 |
| **子任务独立性** | 不一定独立 | 必须独立可执行 |
| **示例** | | |
| | 输入：比较 A 和 B | 输入：比较 A 和 B |
| | 输出：multi_hop + targeted_iterative | 输出：[检索A, 检索B, 对比, 生成答案] |

### 具体例子

**查询：** "If a transaction involves both a connected person and exceeds the size test threshold, what are my disclosure obligations?"

#### Planner（当前）的处理：

```python
# 第 1 步：分类
query_type = "multi_hop"  # 因为有 "both" 和 "and"

# 第 2 步：拆解（字符串分割）
sub_tasks = [
    "If a transaction involves both a connected person",
    "exceeds the size test threshold, what are my disclosure obligations?"
]

# 第 3 步：生成执行计划
execution_plan = {
    "intent": "multi_condition",  # 多条件
    "retrieval_strategy": "targeted_iterative",
    "requires_tool": True,  # 因为有 "size test"
    "answer_format": "concise_with_citations"
}

# 问题：
# - 拆解不完整，第一个子任务缺少谓语
# - 没有识别出这是一个条件判断问题
# - 没有识别出需要同时满足两个条件
```

#### 真正的任务拆解器的处理：

```python
# 第 1 步：语义理解
# 识别：这是一个条件判断问题
# 条件 1：transaction involves connected person
# 条件 2：exceeds size test threshold
# 任务：找出满足两个条件时的披露义务

# 第 2 步：依赖分析
# 任务依赖关系：
# ├─ 检索"关联交易"规则
# ├─ 检索"size test"规则
# ├─ 检索"披露义务"规则
# └─ 综合判断：两个条件都满足时的义务

# 第 3 步：生成原子任务
atomic_tasks = [
    {
        "id": "task_1",
        "type": "retrieval",
        "query": "What is a connected person in HKEX rules?",
        "depends_on": []
    },
    {
        "id": "task_2",
        "type": "retrieval",
        "query": "What is the size test threshold?",
        "depends_on": []
    },
    {
        "id": "task_3",
        "type": "retrieval",
        "query": "What are disclosure obligations for connected transactions?",
        "depends_on": []
    },
    {
        "id": "task_4",
        "type": "retrieval",
        "query": "What are disclosure obligations for transactions exceeding size test?",
        "depends_on": []
    },
    {
        "id": "task_5",
        "type": "reasoning",
        "query": "When both conditions are met, what are the combined disclosure obligations?",
        "depends_on": ["task_1", "task_2", "task_3", "task_4"]
    }
]

# 优点：
# - 每个任务都是独立的、完整的
# - 任务之间的依赖关系明确
# - 可以并行执行不相关的任务
# - 最后的推理任务依赖所有检索结果
```

---

## 三、Planner 的实际工作流程

### 当前 Planner 的流程图

```
用户查询
    ↓
┌─────────────────────────────────────┐
│ 1. 分类（Classification）            │
│    - 检查 direct_indicators          │
│    - 检查 multi_hop_indicators       │
│    - 返回 query_type                 │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. 意图识别（Intent Classification） │
│    - 检查 intent_patterns            │
│    - 返回 intent                     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. 子查询拆解（Sub-query Split）     │
│    - 按 and/or 分割                  │
│    - 返回 sub_queries                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 4. 路由决策（Routing Decision）      │
│    - 决定 retrieval_strategy         │
│    - 决定 requires_tool              │
│    - 决定 answer_format              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 5. 执行计划生成（Plan Generation）   │
│    - 组装 ExecutionPlan              │
│    - 返回给后续节点                  │
└─────────────────────────────────────┘
    ↓
ExecutionPlan（用于路由）
```

### 执行计划的用途

```python
# ExecutionPlan 被后续节点使用

# 1. Retriever 节点使用：
if plan.retrieval_strategy == "single_pass":
    results = retriever.retrieve(query)
elif plan.retrieval_strategy == "multi_query":
    results = retriever.retrieve_for_sub_queries(plan.sub_queries)
elif plan.retrieval_strategy == "targeted_iterative":
    results = retriever.retrieve_iteratively(plan.sub_queries)

# 2. CoverageChecker 节点使用：
coverage = coverage_checker.assess(plan, results)

# 3. ToolExecutor 节点使用（未来）：
if plan.requires_tool:
    tool_result = execute_tool(plan.tool_name, plan.evidence_requirements)

# 4. Reasoning 节点使用：
answer = reasoning_agent.reason(query, plan, results)

# 5. AnswerVerifier 节点使用：
verification = answer_verifier.verify(answer, results)
```

---

## 四、Planner 的三个层次的代码体现

### 第 1 层：路由（主要）

```python
def _determine_retrieval_strategy(self, query_type, intent, needs_second_retrieval):
    """这是路由决策"""
    if query_type == "direct":
        return "single_pass"           # 路由到单次检索
    if needs_second_retrieval or intent == "comparison":
        return "targeted_iterative"    # 路由到迭代检索
    return "multi_query"               # 路由到多查询检索

def _requires_tool(self, intent, query_lower):
    """这也是路由决策"""
    if intent == "calculation_required":
        return True                    # 路由到工具执行
    tool_indicators = ['size test', 'ratio', 'calculate', 'percentage']
    return any(indicator in query_lower for indicator in tool_indicators)

def _determine_answer_format(self, intent, query_type):
    """这也是路由决策"""
    if intent == "comparison":
        return "comparison_table"      # 路由到表格格式
    if intent == "procedure_flow":
        return "checklist_style"       # 路由到清单格式
    return "concise_with_citations"    # 路由到引用格式
```

### 第 2 层：任务拆解（次要）

```python
def _generate_sub_queries(self, query, query_type):
    """这是任务拆解，但很粗糙"""
    if query_type == "direct":
        return [query]                 # 不拆解
    
    # 简单的字符串分割
    parts = re.split(r'\s+(?:and|or)\s+', query, flags=re.IGNORECASE)
    
    if len(parts) > 1:
        return parts                   # 返回拆解后的部分
    else:
        return [query]                 # 拆解失败，返回原查询
```

### 第 3 层：执行计划（新增）

```python
def plan(self, query):
    """生成执行计划"""
    query_type = self._classify_query(query_lower)
    intent = self._classify_intent(query_lower)
    sub_queries = self._generate_sub_queries(query, query_type)
    retrieval_strategy = self._determine_retrieval_strategy(query_type, intent, needs_second_retrieval)
    requires_tool = self._requires_tool(intent, query_lower)
    answer_format = self._determine_answer_format(intent, query_type)
    
    # 组装执行计划
    return PlannerOutput(
        query_type=query_type,
        intent=intent,
        sub_queries=sub_queries,
        retrieval_strategy=retrieval_strategy,
        requires_tool=requires_tool,
        answer_format=answer_format
    )
```

---

## 五、Planner 的局限性

### 为什么 Planner 不是真正的任务拆解器？

#### 1. 拆解粒度太粗

```python
# 当前拆解
query = "What are the disclosure requirements for Rule 14A.35 and Rule 14A.36?"
sub_queries = [
    "What are the disclosure requirements for Rule 14A.35",
    "Rule 14A.36?"  # 不完整！
]

# 真正的拆解应该是
sub_tasks = [
    "Retrieve disclosure requirements for Rule 14A.35",
    "Retrieve disclosure requirements for Rule 14A.36",
    "Compare the two sets of requirements",
    "Generate comprehensive answer"
]
```

#### 2. 拆解方式太简单

```python
# 当前：字符串分割
parts = re.split(r'\s+(?:and|or)\s+', query)

# 应该是：语义理解
# - 识别主语、谓语、宾语
# - 识别逻辑关系（and/or/if-then）
# - 识别隐含的子任务
```

#### 3. 无法处理复杂逻辑

```python
# 当前无法处理
query = "If a transaction involves both a connected person and exceeds the size test, what are my obligations?"

# 应该识别为
# - 条件：connected person AND exceeds size test
# - 任务：找出满足两个条件时的义务
# - 子任务：
#   1. 检索关联交易规则
#   2. 检索 size test 规则
#   3. 检索披露义务规则
#   4. 综合判断
```

#### 4. 无法识别任务依赖

```python
# 当前无法表示
query = "What are the disclosure requirements and how to file them?"

# 应该识别为
tasks = [
    {
        "id": "task_1",
        "type": "retrieval",
        "query": "What are the disclosure requirements?",
        "depends_on": []
    },
    {
        "id": "task_2",
        "type": "retrieval",
        "query": "How to file disclosure?",
        "depends_on": []  # 可以并行执行
    },
    {
        "id": "task_3",
        "type": "reasoning",
        "query": "Combine requirements and filing process",
        "depends_on": ["task_1", "task_2"]  # 依赖前两个任务
    }
]
```

---

## 六、总结

### Planner 的真实身份

```
┌─────────────────────────────────────────────────────────┐
│                    Planner Agent                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  主要职责：问题路由器（Router）                         │
│  ├─ 分类查询类型                                        │
│  ├─ 识别用户意图                                        │
│  ├─ 决定检索策略                                        │
│  ├─ 决定是否需要工具                                    │
│  └─ 决定答案格式                                        │
│                                                         │
│  次要职责：任务拆解器（Task Decomposer）                │
│  ├─ 拆解为子查询（粗糙）                                │
│  ├─ 识别子任务（有限）                                  │
│  └─ 生成执行计划（高层）                                │
│                                                         │
│  新增职责：执行计划生成器（Plan Generator）             │
│  ├─ 组装结构化执行计划                                  │
│  ├─ 为后续节点提供指导                                  │
│  └─ 支持工具调用决策                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 关键结论

| 问题 | 答案 |
|------|------|
| **Planner 是路由器吗？** | ✅ 是的，这是主要职责 |
| **Planner 是任务拆解器吗？** | ⚠️ 部分是，但拆解很粗糙 |
| **Planner 能处理复杂任务吗？** | ❌ 不能，只能处理简单查询 |
| **Planner 的拆解是否独立？** | ❌ 不是，拆解后的子任务不一定独立 |
| **何时需要真正的任务拆解器？** | 当查询变得复杂时（Stage 2/3） |

### 改进方向

**短期（Stage 1）：** 保持当前的路由器设计，扩展规则库

**中期（Stage 2）：** 添加轻量级任务拆解（基于依存句法分析）

**长期（Stage 3）：** 使用 LLM 进行深度任务拆解和依赖分析

---

## 七、代码示例对比

### 当前 Planner 的输出

```python
query = "Compare the disclosure requirements for connected and notifiable transactions"

output = PlannerOutput(
    query_type="multi_hop",
    intent="comparison",
    sub_queries=[
        "Compare the disclosure requirements for connected",
        "notifiable transactions"
    ],
    retrieval_strategy="targeted_iterative",
    requires_tool=False,
    evidence_requirements={
        "Compare the disclosure requirements for connected": "high",
        "notifiable transactions": "high"
    },
    answer_format="comparison_table"
)

# 这个输出告诉后续节点：
# 1. 这是一个多跳查询
# 2. 用户想要比较
# 3. 需要迭代检索
# 4. 答案应该是表格格式
# 但没有告诉后续节点：
# - 具体要比较什么
# - 比较的维度是什么
# - 如何组织答案
```

### 理想的任务拆解输出

```python
query = "Compare the disclosure requirements for connected and notifiable transactions"

output = {
    "query_type": "multi_hop",
    "intent": "comparison",
    "tasks": [
        {
            "id": "task_1",
            "type": "retrieval",
            "description": "Retrieve disclosure requirements for connected transactions",
            "query": "What are the disclosure requirements for connected transactions?",
            "depends_on": [],
            "priority": "high"
        },
        {
            "id": "task_2",
            "type": "retrieval",
            "description": "Retrieve disclosure requirements for notifiable transactions",
            "query": "What are the disclosure requirements for notifiable transactions?",
            "depends_on": [],
            "priority": "high"
        },
        {
            "id": "task_3",
            "type": "reasoning",
            "description": "Compare the two sets of requirements",
            "query": "Compare disclosure requirements: connected vs notifiable",
            "depends_on": ["task_1", "task_2"],
            "priority": "high",
            "comparison_dimensions": [
                "announcement timing",
                "disclosure content",
                "approval requirements",
                "exemptions"
            ]
        }
    ],
    "answer_format": "comparison_table",
    "execution_order": ["task_1", "task_2", "task_3"],
    "parallelizable_tasks": ["task_1", "task_2"]
}

# 这个输出告诉后续节点：
# 1. 有 3 个任务需要执行
# 2. task_1 和 task_2 可以并行执行
# 3. task_3 依赖前两个任务的结果
# 4. 比较的维度是什么
# 5. 答案应该如何组织
```

---

## 八、最终答案

**你的理解是正确的：**

> Planner 本质上是一个问题路由器，而不是将用户的任务拆解成子任务。

**更准确的说法：**

Planner 是一个**混合型组件**：
- **主要职责（70%）：** 问题路由 - 决定如何处理查询
- **次要职责（20%）：** 粗糙的任务拆解 - 按字符串分割
- **新增职责（10%）：** 执行计划生成 - 为后续节点提供指导

真正的**任务拆解器**应该：
- 理解语义和逻辑关系
- 生成独立的、可执行的原子任务
- 识别任务之间的依赖关系
- 支持并行执行

这是 **Stage 2/3** 需要实现的功能。
