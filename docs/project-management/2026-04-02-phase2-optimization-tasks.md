# Phase 2 Agentic RAG 任务分解

> **基于：** `2026-04-02-phase2-optimization-plan.md`  
> **目标：** 将 Phase 2 实施计划分解为可执行的工作流和任务

---

## 工作流概览

Phase 2 包含 3 个主要工作流（Workstream），每个对应一个 Stage：

- **Workstream A**：强化 Agentic Graph（Stage 1）
- **Workstream B**：HKEX 工具集成（Stage 2）
- **Workstream C**：评估与记忆（Stage 3）

---

## Workstream A：强化 Agentic Graph

### A1：规划层升级

- [ ] 定义 `ExecutionPlan` 数据模型（`app/schemas/execution_plan.py`）
- [ ] 定义 `SubTask` 数据模型
- [ ] 扩展意图分类：添加 6-8 个新意图类别
- [ ] 实现意图识别逻辑（启发式）
- [ ] 可选：添加 LLM 辅助意图识别
- [ ] 生成结构化执行计划对象
- [ ] 添加 `requires_tool` 决策逻辑
- [ ] 添加 `evidence_requirements` 生成
- [ ] 更新 `PlannerAgent` 使用新模型
- [ ] 编写单元测试（`tests/test_planner_v2.py`）

### A2：证据覆盖度检查

- [ ] 定义 `CoverageAssessment` 数据模型（`app/schemas/coverage.py`）
- [ ] 创建 `CoverageChecker` 类（`app/agents/coverage_checker.py`）
- [ ] 实现子任务覆盖度评估算法
- [ ] 实现缺失信息识别逻辑
- [ ] 计算覆盖度分数
- [ ] 生成定向检索目标列表
- [ ] 编写单元测试（`tests/test_coverage_checker.py`）

### A3：定向二次检索

- [ ] 创建 `QueryRewriter` 类（`app/retrieval/query_rewriter.py`）
- [ ] 实现基于缺失信息的查询重写
- [ ] 修改 `second_retrieval_node` 接受 `retrieval_targets`
- [ ] 实现针对特定子任务的检索
- [ ] 定义 `RetrievalRound` 数据模型
- [ ] 记录检索历史与原因
- [ ] 更新 `AgentState` 添加 `retrieval_rounds` 字段
- [ ] 编写单元测试（`tests/test_targeted_retrieval.py`）

### A4：证据选择与重排

- [ ] 定义 `SelectedEvidence` 数据模型（`app/schemas/evidence.py`）
- [ ] 创建 `EvidenceSelector` 类（`app/agents/evidence_selector.py`）
- [ ] 实现 chunk 去重算法
- [ ] 实现 rule_number 优先级排序
- [ ] 实现证据多样性保证逻辑
- [ ] 按子任务分组证据
- [ ] 计算多样性分数
- [ ] 编写单元测试（`tests/test_evidence_selector.py`）

### A5：答案验证

- [ ] 定义 `VerificationResult` 数据模型（`app/schemas/verification.py`）
- [ ] 定义 `Contradiction` 数据模型
- [ ] 创建 `AnswerVerifier` 类（`app/agents/answer_verifier.py`）
- [ ] 实现论断提取逻辑
- [ ] 实现论断-引用对齐检查
- [ ] 可选：实现矛盾检测
- [ ] 计算置信度
- [ ] 生成修订建议
- [ ] 编写单元测试（`tests/test_answer_verifier.py`）

### A6：工作流集成

- [ ] 更新 `AgentState` 添加所有新字段（`app/agents/graph_state.py`）
- [ ] 创建 `coverage_checker_node`
- [ ] 创建 `evidence_selector_node`
- [ ] 创建 `answer_verifier_node`
- [ ] 更新条件路由逻辑
- [ ] 可选：添加验证失败的修订分支
- [ ] 更新 `LangGraphOrchestrator`
- [ ] 编写集成测试（`tests/test_workflow_v2.py`）

### A7：API 响应增强

- [ ] 定义 `ExecutionTrace` 数据模型（`app/schemas/trace.py`）
- [ ] 更新 `ChatResponse` 添加新字段（`app/schemas/response.py`）
- [ ] 更新 `/chat` 端点返回新字段
- [ ] 更新 API 文档
- [ ] 编写 API 测试（`tests/test_api_v2.py`）

### A8：文档与示例

- [ ] 更新 README 说明新功能
- [ ] 创建 3 个 demo queries 展示新能力
- [ ] 编写 Stage 1 设计文档
- [ ] 更新 API 文档

---

## Workstream B：HKEX 工具集成

### B1：工具基础设施

- [ ] 定义 `ToolResult` 数据模型（`app/schemas/tool.py`）
- [ ] 定义 `ToolCall` 数据模型
- [ ] 扩展 `BaseTool` 添加 `description` 属性
- [ ] 扩展 `BaseTool` 添加 `input_schema` 属性
- [ ] 添加 `validate_inputs` 方法
- [ ] 创建工具注册机制（`app/tools/registry.py`）
- [ ] 编写单元测试（`tests/test_tool_base.py`）

### B2：Size Test Calculator 工具

- [ ] 创建 `SizeTestCalculatorTool` 类（`app/tools/size_test_calculator.py`）
- [ ] 实现资产比率计算
- [ ] 实现收益比率计算
- [ ] 实现收入比率计算
- [ ] 实现代价比率计算
- [ ] 实现股本比率计算
- [ ] 实现交易分类逻辑
- [ ] 实现披露要求映射
- [ ] 添加输入验证
- [ ] 编写单元测试（`tests/test_size_test_calculator.py`）
- [ ] 编写使用文档

### B3：Rule Lookup 工具

- [ ] 创建 `RuleLookupTool` 类（`app/tools/rule_lookup.py`）
- [ ] 实现按 rule_number 精确查找
- [ ] 实现相关规则查找
- [ ] 返回完整条款文本与元数据
- [ ] 可选：添加缓存机制
- [ ] 编写单元测试（`tests/test_rule_lookup.py`）
- [ ] 编写使用文档

### B4：Disclosure Checklist 工具

- [ ] 创建 `DisclosureChecklistTool` 类（`app/tools/disclosure_checklist.py`）
- [ ] 定义披露清单模板
- [ ] 实现基于交易类型的清单生成
- [ ] 添加时间线/截止日期
- [ ] 映射适用规则
- [ ] 编写单元测试（`tests/test_disclosure_checklist.py`）
- [ ] 编写使用文档

### B5：Transaction Classifier 工具

- [ ] 创建 `TransactionClassifierTool` 类（`app/tools/transaction_classifier.py`）
- [ ] 实现关联方识别逻辑
- [ ] 实现关联交易判断
- [ ] 映射适用章节
- [ ] 识别可能的豁免
- [ ] 编写单元测试（`tests/test_transaction_classifier.py`）
- [ ] 编写使用文档

### B6：工具执行器

- [ ] 创建 `ToolExecutor` 类（`app/agents/tool_executor.py`）
- [ ] 实现工具调用逻辑
- [ ] 实现工具输入准备
- [ ] 实现工具输出解析
- [ ] 添加错误处理与回退
- [ ] 记录工具调用历史
- [ ] 编写单元测试（`tests/test_tool_executor.py`）

### B7：Planner 工具决策

- [ ] 更新 `PlannerAgent` 添加工具需求识别
- [ ] 实现工具选择逻辑
- [ ] 生成工具输入提示
- [ ] 更新 `ExecutionPlan` 包含工具信息
- [ ] 编写单元测试

### B8：工作流工具集成

- [ ] 添加工具路由条件到 workflow
- [ ] 创建 `tool_executor_node`
- [ ] 实现 tool-only 分支
- [ ] 实现 tool+retrieval 并行分支
- [ ] 更新 `reasoning_node` 融合工具输出
- [ ] 编写集成测试（`tests/test_tool_workflow.py`）

### B9：API 工具响应

- [ ] 更新 `ChatResponse` 添加 `tool_calls` 字段
- [ ] 更新 `/chat` 端点返回工具信息
- [ ] 更新 API 文档
- [ ] 编写 API 测试

### B10：文档与示例

- [ ] 创建工具使用指南
- [ ] 创建 2 个工具调用 demo queries
- [ ] 更新 README
- [ ] 更新 API 文档

---

## Workstream C：评估与记忆

### C1：评估数据集

- [ ] 设计评估问题模板
- [ ] 标注 10 个 direct 问题
- [ ] 标注 10 个 multi_hop 问题
- [ ] 标注 5 个需要工具的问题
- [ ] 标注预期规则列表
- [ ] 标注预期答案（gold answer）
- [ ] 创建 `data/evaluation/benchmark.json`
- [ ] 编写数据集文档（`data/evaluation/README.md`）

### C2：评估指标

- [ ] 创建 `Metrics` 类（`app/evaluation/metrics.py`）
- [ ] 实现检索 Recall@k 计算
- [ ] 实现引用质量评估
- [ ] 实现答案质量评估
- [ ] 实现工具使用评估
- [ ] 编写单元测试（`tests/test_metrics.py`）

### C3：评估脚本

- [ ] 创建评估脚本（`scripts/evaluate.py`）
- [ ] 实现批量问题运行
- [ ] 实现指标计算
- [ ] 生成评估报告（JSON + Markdown）
- [ ] 添加命令行参数
- [ ] 编写使用文档

### C4：失败分析

- [ ] 定义失败类别枚举
- [ ] 创建 `FailureAnalyzer` 类（`app/evaluation/failure_analysis.py`）
- [ ] 实现失败分类逻辑
- [ ] 生成失败案例报告
- [ ] 添加改进建议生成
- [ ] 编写文档

### C5：对话记忆

- [ ] 定义 `ConversationMemory` 数据模型（`app/schemas/memory.py`）
- [ ] 定义 `CaseContext` 数据模型
- [ ] 定义 `Message` 数据模型
- [ ] 创建 `ConversationMemory` 类（`app/memory/conversation_memory.py`）
- [ ] 实现内存存储
- [ ] 可选：实现 Redis 存储
- [ ] 实现上下文更新逻辑
- [ ] 添加会话过期机制
- [ ] 编写单元测试（`tests/test_memory.py`）

### C6：API 会话支持

- [ ] 更新 `QueryRequest` 添加 `session_id` 参数
- [ ] 更新 `QueryRequest` 添加 `case_context` 参数
- [ ] 更新 `ChatResponse` 添加会话信息
- [ ] 更新 `/chat` 端点加载会话
- [ ] 实现上下文传递到 workflow
- [ ] 编写 API 测试（`tests/test_session_api.py`）

### C7：执行追踪

- [ ] 定义 `ExecutionTrace` 完整模型（`app/schemas/trace.py`）
- [ ] 定义 `NodeExecution` 数据模型
- [ ] 在每个 node 记录输入输出
- [ ] 记录决策点与原因
- [ ] 记录时间戳
- [ ] 可选：生成可视化追踪
- [ ] 编写文档

### C8：性能监控

- [ ] 创建 `Metrics` 类（`app/monitoring/metrics.py`）
- [ ] 添加响应时间监控
- [ ] 添加检索性能监控
- [ ] 添加工具调用监控
- [ ] 添加错误率监控
- [ ] 可选：导出 Prometheus 指标
- [ ] 更新 `main.py` 集成监控
- [ ] 编写文档

### C9：文档与示例

- [ ] 创建多轮对话 demo
- [ ] 创建评估报告示例
- [ ] 更新 README
- [ ] 编写完整系统文档

---

## 建议执行顺序

### 第 1-2 周
- A1：规划层升级
- A2：证据覆盖度检查
- A3：定向二次检索

### 第 3-4 周
- A4：证据选择与重排
- A5：答案验证
- A6：工作流集成（部分）

### 第 5-6 周
- A6：工作流集成（完成）
- A7：API 响应增强
- A8：文档与示例
- **Stage 1 验收**

### 第 7-8 周
- B1：工具基础设施
- B2：Size Test Calculator 工具
- B3：Rule Lookup 工具
- B4：Disclosure Checklist 工具

### 第 9-10 周
- B5：Transaction Classifier 工具
- B6：工具执行器
- B7：Planner 工具决策
- B8：工作流工具集成

### 第 11 周
- B9：API 工具响应
- B10：文档与示例
- **Stage 2 验收**

### 第 12 周
- C1：评估数据集
- C2：评估指标
- C3：评估脚本
- C4：失败分析

### 第 13 周
- C5：对话记忆
- C6：API 会话支持
- C7：执行追踪
- C8：性能监控
- C9：文档与示例
- **Stage 3 验收**

---

## 里程碑检查点

### Milestone 1：规划与检索增强（Week 4）
- [ ] Planner 输出 ExecutionPlan
- [ ] 证据覆盖度检查工作
- [ ] 定向二次检索工作
- [ ] 单元测试通过

### Milestone 2：验证与工作流（Week 6）
- [ ] 证据选择器工作
- [ ] 答案验证器工作
- [ ] 新工作流完整运行
- [ ] 至少 3 个 demo queries

### Milestone 3：工具基础（Week 8）
- [ ] 至少 2 个工具实现
- [ ] 工具单元测试通过
- [ ] 工具文档完成

### Milestone 4：工具集成（Week 10）
- [ ] 工作流支持工具调用
- [ ] 至少 2 个工具调用 demo
- [ ] 工具与检索融合工作

### Milestone 5：评估体系（Week 12）
- [ ] 评估数据集完成
- [ ] 评估脚本可运行
- [ ] 生成评估报告

### Milestone 6：完整系统（Week 13）
- [ ] 支持多轮对话
- [ ] 执行追踪完整
- [ ] 所有文档更新
- [ ] **Phase 2 完成**

---

## 依赖关系

```
A1 (Planner) ──▶ A2 (Coverage) ──▶ A3 (Retrieval)
                                      │
                                      ▼
A4 (Evidence) ──▶ A5 (Verifier) ──▶ A6 (Workflow) ──▶ A7 (API)
                                                        │
                                                        ▼
B1 (Tool Base) ──▶ B2-B5 (Tools) ──▶ B6 (Executor) ──▶ B7 (Planner)
                                                        │
                                                        ▼
                                      B8 (Workflow) ──▶ B9 (API)
                                                        │
                                                        ▼
C1 (Dataset) ──▶ C2-C3 (Eval) ──▶ C4 (Analysis)
                                      │
C5 (Memory) ──▶ C6 (API) ─────────────┤
                                      │
C7 (Trace) ──▶ C8 (Monitor) ─────────┴──▶ C9 (Docs)
```

---

## 可选任务（时间允许时）

- [ ] LLM 辅助意图识别（A1）
- [ ] 矛盾检测（A5）
- [ ] 验证失败修订分支（A6）
- [ ] 工具输出缓存（B3）
- [ ] Redis 会话存储（C5）
- [ ] 可视化执行追踪（C7）
- [ ] Prometheus 指标导出（C8）

---

## 总结

Phase 2 任务分解包含：
- **3 个主要工作流**
- **约 100+ 个具体任务**
- **6 个里程碑检查点**
- **13 周实施周期**

每个任务都有明确的交付物和验收标准，便于跟踪进度和质量控制。
