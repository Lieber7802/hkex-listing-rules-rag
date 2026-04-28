# Phase 2 Agentic RAG 优化实施计划

> **基于：** `2026-04-02-phase2-optimization-design.md`  
> **目标：** 分阶段实施 Phase 2 优化，将系统从最小可行原型升级为真正的 Agentic RAG 系统

---

## 实施策略

Phase 2 分为三个递进阶段，每个阶段独立可交付：

- **Stage 1（4-6 周）**：强化现有 graph 的 agentic 能力
- **Stage 2（3-4 周）**：集成 HKEX 专用工具
- **Stage 3（2-3 周）**：建立评估与记忆系统

总计：**9-13 周**

---

## Stage 1：强化 Agentic Graph

### 目标

让 LangGraph 工作流从"结构上 agentic"变为"行为上 agentic"。

### 任务清单

#### Task 1.1：升级 Planner 为执行控制器

**文件：**
- 修改：`app/schemas/query.py`
- 修改：`app/agents/planner_agent.py`
- 新建：`app/schemas/execution_plan.py`

**步骤：**
- [ ] 定义 `ExecutionPlan` 数据模型
- [ ] 定义 `SubTask` 数据模型
- [ ] 扩展意图分类：增加 6-8 个新意图类别
- [ ] 实现意图识别逻辑（启发式 + 可选 LLM）
- [ ] 生成结构化执行计划对象
- [ ] 添加 `requires_tool` 决策逻辑
- [ ] 添加 `evidence_requirements` 生成逻辑
- [ ] 编写单元测试

**验收：**
- Planner 输出 `ExecutionPlan` 而非 `PlannerOutput`
- 至少能识别 6 种意图
- 测试覆盖率 > 80%

#### Task 1.2：实现证据覆盖度检查器

**文件：**
- 新建：`app/agents/coverage_checker.py`
- 新建：`app/schemas/coverage.py`

**步骤：**
- [ ] 定义 `CoverageAssessment` 数据模型
- [ ] 实现子任务覆盖度评估逻辑
- [ ] 实现缺失信息识别
- [ ] 计算覆盖度分数
- [ ] 生成定向检索目标
- [ ] 编写单元测试

**验收：**
- 能评估每个子任务的证据充分性
- 能识别缺失信息
- 输出 `CoverageAssessment` 对象

#### Task 1.3：实现定向二次检索

**文件：**
- 修改：`app/agents/langgraph_workflow.py`
- 新建：`app/retrieval/query_rewriter.py`

**步骤：**
- [ ] 实现 query rewriting 逻辑（可选）
- [ ] 修改 `second_retrieval_node` 接受 `retrieval_targets`
- [ ] 针对未覆盖子任务生成新查询
- [ ] 记录检索轮次与原因
- [ ] 更新 `AgentState` 添加 `retrieval_rounds` 字段
- [ ] 编写单元测试

**验收：**
- 二次检索基于 `CoverageAssessment` 触发
- 能针对特定子任务检索
- 检索历史可追溯

#### Task 1.4：实现证据选择器

**文件：**
- 新建：`app/agents/evidence_selector.py`
- 新建：`app/schemas/evidence.py`

**步骤：**
- [ ] 定义 `SelectedEvidence` 数据模型
- [ ] 实现 chunk 去重逻辑
- [ ] 实现 rule_number 优先级排序
- [ ] 实现证据多样性保证
- [ ] 按子任务分组证据
- [ ] 计算多样性分数
- [ ] 编写单元测试

**验收：**
- 能去除高度重叠的 chunks
- 优先保留带 rule_number 的 chunks
- 证据覆盖多个章节/规则

#### Task 1.5：实现答案验证器

**文件：**
- 新建：`app/agents/answer_verifier.py`
- 新建：`app/schemas/verification.py`

**步骤：**
- [ ] 定义 `VerificationResult` 数据模型
- [ ] 实现论断提取逻辑
- [ ] 实现论断-引用对齐检查
- [ ] 实现矛盾检测（可选）
- [ ] 计算置信度
- [ ] 生成修订建议
- [ ] 编写单元测试

**验收：**
- 能识别答案中的主要论断
- 能检查每个论断是否有支撑
- 输出置信度评估

#### Task 1.6：更新 LangGraph 工作流

**文件：**
- 修改：`app/agents/langgraph_workflow.py`
- 修改：`app/agents/graph_state.py`

**步骤：**
- [ ] 更新 `AgentState` 添加新字段
- [ ] 添加 `coverage_checker_node`
- [ ] 添加 `evidence_selector_node`
- [ ] 添加 `answer_verifier_node`
- [ ] 更新条件路由逻辑
- [ ] 添加验证失败的修订分支（可选）
- [ ] 更新 orchestrator
- [ ] 编写集成测试

**验收：**
- 新工作流能完整运行
- 所有新节点正常工作
- 至少一个 demo query 展示完整 trace

#### Task 1.7：更新 API 响应

**文件：**
- 修改：`app/schemas/response.py`
- 修改：`app/api/chat.py`

**步骤：**
- [ ] 添加 `execution_trace` 字段
- [ ] 添加 `retrieval_rounds` 字段
- [ ] 添加 `coverage_assessment` 字段
- [ ] 添加 `confidence_level` 字段
- [ ] 添加 `verification_result` 字段
- [ ] 更新 API 文档
- [ ] 编写 API 测试

**验收：**
- API 响应包含所有新字段
- 字段内容正确填充
- API 文档更新

### Stage 1 里程碑

**完成标准：**
- [ ] 所有 Task 1.1-1.7 完成
- [ ] 单元测试通过率 > 85%
- [ ] 至少 3 个 demo queries 展示新能力
- [ ] 文档更新完成

**预期时间：** 4-6 周

---

## Stage 2：HKEX 专用工具集成

### 目标

让系统能处理需要计算和结构化输出的 HKEX 合规任务。

### 任务清单

#### Task 2.1：扩展工具基类

**文件：**
- 修改：`app/tools/base_tool.py`
- 新建：`app/schemas/tool.py`

**步骤：**
- [ ] 定义 `ToolResult` 数据模型
- [ ] 定义 `ToolCall` 数据模型
- [ ] 扩展 `BaseTool` 添加 `description` 和 `input_schema`
- [ ] 添加 `validate_inputs` 方法
- [ ] 编写工具注册机制
- [ ] 编写单元测试

**验收：**
- `BaseTool` 接口完整
- 支持输入验证
- 支持工具注册

#### Task 2.2：实现 SizeTestCalculatorTool

**文件：**
- 新建：`app/tools/size_test_calculator.py`

**步骤：**
- [ ] 实现五大比率计算逻辑
- [ ] 实现交易分类逻辑
- [ ] 实现披露要求映射
- [ ] 添加输入验证
- [ ] 编写单元测试
- [ ] 编写使用文档

**验收：**
- 能正确计算五大比率
- 能正确分类交易类型
- 测试覆盖所有边界情况

#### Task 2.3：实现 RuleLookupTool

**文件：**
- 新建：`app/tools/rule_lookup.py`

**步骤：**
- [ ] 实现按 rule_number 精确查找
- [ ] 实现相关规则查找
- [ ] 返回完整条款文本
- [ ] 添加缓存机制（可选）
- [ ] 编写单元测试

**验收：**
- 能按 rule_number 精确查找
- 返回完整元数据
- 查找速度 < 100ms

#### Task 2.4：实现 DisclosureChecklistTool

**文件：**
- 新建：`app/tools/disclosure_checklist.py`

**步骤：**
- [ ] 定义披露清单模板
- [ ] 实现基于交易类型的清单生成
- [ ] 添加时间线/截止日期
- [ ] 映射适用规则
- [ ] 编写单元测试

**验收：**
- 能生成结构化清单
- 清单项完整准确
- 包含时间要求

#### Task 2.5：实现 TransactionClassifierTool

**文件：**
- 新建：`app/tools/transaction_classifier.py`

**步骤：**
- [ ] 实现关联方识别逻辑
- [ ] 实现关联交易判断
- [ ] 映射适用章节
- [ ] 识别可能的豁免
- [ ] 编写单元测试

**验收：**
- 能判断是否为关联交易
- 能识别关联类型
- 能列出适用规则

#### Task 2.6：实现工具执行器节点

**文件：**
- 新建：`app/agents/tool_executor.py`

**步骤：**
- [ ] 实现工具调用逻辑
- [ ] 实现工具输入准备
- [ ] 实现工具输出解析
- [ ] 添加错误处理
- [ ] 记录工具调用历史
- [ ] 编写单元测试

**验收：**
- 能正确调用工具
- 能处理工具错误
- 工具调用可追溯

#### Task 2.7：更新 Planner 工具决策

**文件：**
- 修改：`app/agents/planner_agent.py`

**步骤：**
- [ ] 添加工具需求识别逻辑
- [ ] 实现工具选择逻辑
- [ ] 生成工具输入提示
- [ ] 更新 `ExecutionPlan` 包含工具信息
- [ ] 编写单元测试

**验收：**
- Planner 能决策 `requires_tool`
- 能选择正确的工具
- 能生成工具输入提示

#### Task 2.8：更新工作流支持工具分支

**文件：**
- 修改：`app/agents/langgraph_workflow.py`

**步骤：**
- [ ] 添加工具路由条件
- [ ] 添加 `tool_executor_node`
- [ ] 实现 tool-only 分支
- [ ] 实现 tool+retrieval 并行分支
- [ ] 更新 reasoning 节点融合工具输出
- [ ] 编写集成测试

**验收：**
- 工作流支持三种路径（retrieval-only, tool-only, hybrid）
- 工具输出与检索证据能融合
- 至少一个 demo query 调用工具

#### Task 2.9：更新 API 响应

**文件：**
- 修改：`app/schemas/response.py`
- 修改：`app/api/chat.py`

**步骤：**
- [ ] 添加 `tool_calls` 字段
- [ ] 更新响应序列化
- [ ] 更新 API 文档
- [ ] 编写 API 测试

**验收：**
- API 响应包含工具调用信息
- 工具输出正确展示

### Stage 2 里程碑

**完成标准：**
- [ ] 至少实现 2 个工具（SizeTestCalculator + RuleLookup）
- [ ] 工作流支持工具调用
- [ ] 至少 2 个 demo queries 调用工具
- [ ] 工具文档完整

**预期时间：** 3-4 周

---

## Stage 3：评估、记忆与可观测性

### 目标

建立评估体系、支持多轮对话、增强系统可观测性。

### 任务清单

#### Task 3.1：构建评估数据集

**文件：**
- 新建：`data/evaluation/benchmark.json`
- 新建：`data/evaluation/README.md`

**步骤：**
- [ ] 设计评估问题模板
- [ ] 标注 20-30 个测试问题
- [ ] 覆盖所有意图类型
- [ ] 包含需要工具的问题
- [ ] 标注预期规则和答案
- [ ] 编写数据集文档

**验收：**
- 至少 20 个标注问题
- 覆盖 direct 和 multi_hop
- 至少 5 个需要工具

#### Task 3.2：实现评估脚本

**文件：**
- 新建：`scripts/evaluate.py`
- 新建：`app/evaluation/metrics.py`

**步骤：**
- [ ] 实现检索 Recall@k 计算
- [ ] 实现引用质量评估
- [ ] 实现答案质量评估
- [ ] 实现工具使用评估
- [ ] 生成评估报告
- [ ] 编写使用文档

**验收：**
- 能运行完整评估
- 输出结构化指标
- 生成可读报告

#### Task 3.3：实现失败分析

**文件：**
- 修改：`scripts/evaluate.py`
- 新建：`app/evaluation/failure_analysis.py`

**步骤：**
- [ ] 定义失败类别
- [ ] 实现失败分类逻辑
- [ ] 生成失败案例报告
- [ ] 添加改进建议
- [ ] 编写文档

**验收：**
- 能自动分类失败原因
- 生成失败案例列表
- 提供改进建议

#### Task 3.4：实现对话记忆

**文件：**
- 新建：`app/memory/conversation_memory.py`
- 新建：`app/schemas/memory.py`

**步骤：**
- [ ] 定义 `ConversationMemory` 数据模型
- [ ] 定义 `CaseContext` 数据模型
- [ ] 实现会话存储（内存/Redis）
- [ ] 实现上下文更新逻辑
- [ ] 添加会话过期机制
- [ ] 编写单元测试

**验收：**
- 支持多轮对话
- 能维护案件上下文
- 会话可持久化

#### Task 3.5：更新 API 支持会话

**文件：**
- 修改：`app/api/chat.py`
- 修改：`app/schemas/query.py`
- 修改：`app/schemas/response.py`

**步骤：**
- [ ] 添加 `session_id` 参数
- [ ] 添加 `case_context` 参数
- [ ] 实现会话加载逻辑
- [ ] 实现上下文传递
- [ ] 更新响应包含会话信息
- [ ] 编写 API 测试

**验收：**
- API 支持 `session_id`
- 多轮对话正常工作
- 上下文正确维护

#### Task 3.6：增强执行追踪

**文件：**
- 新建：`app/schemas/trace.py`
- 修改：`app/agents/langgraph_workflow.py`

**步骤：**
- [ ] 定义 `ExecutionTrace` 数据模型
- [ ] 记录每个节点的输入输出
- [ ] 记录决策点与原因
- [ ] 记录时间戳
- [ ] 生成可视化追踪（可选）
- [ ] 编写文档

**验收：**
- 完整记录执行过程
- 追踪信息结构化
- 便于调试

#### Task 3.7：添加性能监控

**文件：**
- 新建：`app/monitoring/metrics.py`
- 修改：`app/main.py`

**步骤：**
- [ ] 添加响应时间监控
- [ ] 添加检索性能监控
- [ ] 添加工具调用监控
- [ ] 添加错误率监控
- [ ] 导出 Prometheus 指标（可选）
- [ ] 编写文档

**验收：**
- 关键指标可监控
- 性能瓶颈可识别

### Stage 3 里程碑

**完成标准：**
- [ ] 评估脚本可运行
- [ ] 至少 20 个问题的 benchmark
- [ ] API 支持多轮对话
- [ ] 执行追踪完整

**预期时间：** 2-3 周

---

## 总体时间线

```
Week 1-2:   Task 1.1-1.3 (Planner + Coverage + Retrieval)
Week 3-4:   Task 1.4-1.6 (Evidence + Verifier + Workflow)
Week 5-6:   Task 1.7 + Stage 1 测试与文档
Week 7-8:   Task 2.1-2.5 (工具实现)
Week 9-10:  Task 2.6-2.9 (工具集成)
Week 11-12: Task 3.1-3.4 (评估 + 记忆)
Week 13:    Task 3.5-3.7 + 最终测试

总计：13 周（约 3 个月）
```

---

## 资源需求

### 人力

- **1 名开发者**：全职
- **1 名领域专家**（兼职）：标注评估数据、验证工具逻辑

### 计算资源

- 本地开发机器（Phase 1 配置即可）
- 可选：Redis 服务器（用于会话存储）

---

## 风险管理

### 风险 1：复杂度失控

**缓解措施：**
- 严格按 Stage 递进，不跨阶段开发
- 每个 Stage 独立验收
- 保持代码简洁，避免过度抽象

### 风险 2：工具输出不可靠

**缓解措施：**
- 工具输出附带置信度
- 工具调用可回退到纯检索
- 充分的单元测试

### 风险 3：评估成本过高

**缓解措施：**
- 只做轻量 benchmark（20-30 题）
- 不追求完整 RAGAS
- 优先人工标注关键案例

### 风险 4：时间超期

**缓解措施：**
- 每个 Stage 设置缓冲时间
- 可选功能明确标记
- 必要时缩减 Stage 3 范围

---

## 验收与交付

### Stage 1 交付物

- [ ] 更新的代码库
- [ ] 单元测试（覆盖率 > 85%）
- [ ] 至少 3 个 demo queries
- [ ] 更新的 README
- [ ] Stage 1 设计文档

### Stage 2 交付物

- [ ] 至少 2 个可用工具
- [ ] 工具使用文档
- [ ] 至少 2 个工具调用 demo
- [ ] 更新的 API 文档

### Stage 3 交付物

- [ ] 评估数据集（20+ 问题）
- [ ] 评估脚本与报告
- [ ] 多轮对话 demo
- [ ] 完整的系统文档

---

## 后续维护

Phase 2 完成后，建议：

1. **持续评估**：定期运行 benchmark，跟踪指标变化
2. **工具扩展**：根据用户反馈增加新工具
3. **数据集扩充**：逐步增加评估问题
4. **性能优化**：基于监控数据优化瓶颈

---

## 总结

Phase 2 实施计划将系统从 Phase 1 的最小可行原型升级为真正的 Agentic RAG 系统。

关键里程碑：
- **Week 6**：Stage 1 完成，系统具备真实 agentic 能力
- **Week 10**：Stage 2 完成，系统支持工具调用
- **Week 13**：Stage 3 完成，系统具备评估与记忆能力

预期成果：一个可用的、可评估的、可扩展的 HKEX 合规助手。
