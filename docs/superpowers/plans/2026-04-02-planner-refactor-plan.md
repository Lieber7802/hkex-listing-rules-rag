# Planner 重构实施计划

> **基于：** `2026-04-02-phase2-optimization-design.md` 第 6.5 节  
> **目标：** 将 Planner 从启发式规则升级为 LLM 主导、启发式兜底与校验的双节点架构

---

## 实施策略

采用 TDD 方式，按以下顺序实施：

1. 先定义 schema（数据模型）
2. 编写失败测试
3. 实现最小代码通过测试
4. 集成到 LangGraph 工作流
5. 运行完整测试套件

---

## 任务清单

### Task 1: 定义新的 Schema

**文件：**
- 新建：`app/schemas/planning.py`

**步骤：**
- [ ] 定义 `RouteDecision` 模型
- [ ] 定义 `ToolDecision` 模型
- [ ] 定义 `SubTask` 模型
- [ ] 定义 `DecompositionPlan` 模型
- [ ] 定义 `RouteValidationResult` 模型
- [ ] 定义 `DecompositionValidationResult` 模型

### Task 2: 实现 LLMRoutePlanner

**文件：**
- 新建：`app/agents/llm_route_planner.py`
- 测试：`tests/test_llm_route_planner.py`

**步骤：**
- [ ] 编写失败测试
- [ ] 实现 `LLMRoutePlanner` 类
- [ ] 实现 LLM 调用逻辑
- [ ] 实现 JSON 解析与验证
- [ ] 实现 fallback 机制
- [ ] 确保测试通过

### Task 3: 实现 HeuristicRouteValidator

**文件：**
- 新建：`app/agents/route_validator.py`
- 测试：`tests/test_route_validator.py`

**步骤：**
- [ ] 编写失败测试
- [ ] 实现路由校验规则
- [ ] 实现冲突检测
- [ ] 实现告警生成
- [ ] 确保测试通过

### Task 4: 实现 TaskDecomposer

**文件：**
- 新建：`app/agents/task_decomposer.py`
- 测试：`tests/test_task_decomposer.py`

**步骤：**
- [ ] 编写失败测试
- [ ] 实现 `TaskDecomposer` 类
- [ ] 实现 LLM 调用逻辑
- [ ] 实现子任务生成
- [ ] 实现依赖关系建模
- [ ] 实现 fallback 机制
- [ ] 确保测试通过

### Task 5: 实现 DecompositionValidator

**文件：**
- 新建：`app/agents/decomposition_validator.py`
- 测试：`tests/test_decomposition_validator.py`

**步骤：**
- [ ] 编写失败测试
- [ ] 实现拆解校验规则
- [ ] 实现依赖图检查
- [ ] 实现残句检测
- [ ] 确保测试通过

### Task 6: 更新 GraphState

**文件：**
- 修改：`app/agents/graph_state.py`

**步骤：**
- [ ] 添加 `route_decision` 字段
- [ ] 添加 `decomposition_plan` 字段
- [ ] 添加 `validation_warnings` 字段

### Task 7: 更新 LangGraph 工作流

**文件：**
- 修改：`app/agents/langgraph_workflow.py`

**步骤：**
- [ ] 添加 `llm_route_planner_node`
- [ ] 添加 `route_validator_node`
- [ ] 添加 `task_decomposer_node`
- [ ] 添加 `decomposition_validator_node`
- [ ] 更新条件路由逻辑
- [ ] 实现简单问题跳过拆解的分支

### Task 8: 更新 API 响应

**文件：**
- 修改：`app/schemas/response.py`
- 修改：`app/api/chat.py`

**步骤：**
- [ ] 添加 `route_decision` 字段
- [ ] 添加 `decomposition_plan` 字段
- [ ] 更新 API 返回逻辑

### Task 9: 编写集成测试

**文件：**
- 新建：`tests/test_planner_integration.py`

**步骤：**
- [ ] 测试简单查询跳过拆解
- [ ] 测试复杂查询进入拆解
- [ ] 测试 fallback 机制
- [ ] 测试校验告警

### Task 10: 更新文档

**文件：**
- 更新：`README.md`
- 更新：`README-zh.md`

**步骤：**
- [ ] 说明新的 Planner 架构
- [ ] 说明配置选项
- [ ] 提供示例

---

## 验收标准

- [ ] 所有新测试通过
- [ ] 所有现有测试仍通过
- [ ] 简单查询可跳过拆解
- [ ] 复杂查询正确拆解
- [ ] fallback 机制工作正常
- [ ] 校验告警正确生成
- [ ] 文档已更新

---

## 时间估算

- Task 1-2: 2-3 小时
- Task 3-5: 2-3 小时
- Task 6-8: 2-3 小时
- Task 9-10: 1-2 小时

**总计：7-11 小时**
