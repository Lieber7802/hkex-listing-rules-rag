# HKEX Agentic RAG 优化说明

> 范围：本文档主要基于项目的 Markdown 文档整理，并补充对当前 agent、检索与 API 相关代码做了有限查阅，用于验证文档中描述的 Agentic RAG 能力是否在实现中真实体现。

## 1. 总体判断

当前 Phase 1 系统是一个合格的最小可行（MVP）Agentic RAG 原型，但其 Agentic 能力仍偏单薄。

这并不是对 Phase 1 范围的否定。事实上，当前实现与 `README.md`、`README-zh.md`、`spec.md` 中的 Phase 1 目标基本一致：构建一个小型、可本地运行、可测试的后端，包含一个 planner 步骤、混合检索、基于证据的回答与引用。

但如果问题是：系统是否已经在“比单次检索的 RAG 稍微增强”之外达到“足够 agentic”的程度，答案是：还没有。

当前系统更接近：

- 混合检索 RAG
- 加一个轻量的查询分类/路由
- 再加一个可选的额外检索轮次

而不是一个具备明确规划、执行、验证与自适应控制的更强 agentic 系统。

## 2. 为什么会显得单薄

### 2.1 Planner 仍然偏浅

从文档与代码来看，Planner 当前主要做三件事：

- 将查询分类为 `direct` 或 `multi_hop`
- 将部分查询拆成简单的子查询
- 决定是否可能需要二次检索

这些是有价值的，但仍然狭窄。它尚未做到：

- 在两类标签之外识别更细的意图类别
- 产出真正的执行计划（execution plan）
- 显式推理“缺失证据”是什么
- 针对子任务选择不同的检索策略
- 决定是否应调用工具

因此，Planner 在行为上更像“路由启发式规则”，而不是“真正的规划组件”。

### 2.2 二次检索还不是自适应检索循环

LangGraph 工作流包含 `Planner -> Retriever -> Conditional Router -> Second Retrieval -> Reasoning`，这在 Phase 1 是一个不错的结构。

但根据 `app/agents/langgraph_workflow.py`，当前的二次检索步骤基本是在原始 query 上再跑一次检索，并追加之前未出现的 chunks。它尚未做到：

- 重写 query
- 针对“未覆盖的子问题”进行定向检索
- 检查问题的哪些部分仍然缺乏支持
- 动态收缩/扩张检索策略
- 基于证据充分性停止，而不是固定“一次额外轮次”

因此，图结构看起来更先进，但实际检索控制策略还不够自适应。

### 2.3 推理步骤能综合，但不验证

Reasoning agent 能从检索证据生成答案并附带引用，这是 Phase 1 的正确基线。

但根据 `app/agents/reasoning_agent.py`，当前尚未强制更严格的证据纪律，例如：

- 论断与引用的对齐（claim-to-citation alignment）
- 对每个子查询做覆盖度检查
- 跨 chunk 的矛盾检测
- 当证据偏弱/不完整时的答案修订
- 在缺少支撑证据时的明确拒答/保守输出

这使系统在“格式上引用可追溯”，但在“行为上未证据验证”。

### 2.4 系统还没有工具使用

文档明确把 `app/tools/` 留作 Phase 2，`app/tools/base_tool.py` 也表明工具集成目前只是接口桩。

这意味着当前系统无法：

- 调用 size test calculator
- 执行结构化决策过程
- 有选择地调用文档查找工具
- 将符号化/结构化输出与检索到的文本证据融合

对 HKEX 合规场景来说，这是最关键的缺失之一，因为许多实务问题并不只是叙述性检索就能解决。

### 2.5 没有对话记忆或案件状态

当前 API 基本是单轮：一个 query 输入，一个 response 输出。

这对 Phase 1 可接受，但会限制系统在真实合规工作流中的适用性，例如用户可能会：

- 追问澄清问题
- 基于上一轮答案继续缩小范围
- 给出越来越多的案件事实并要求结合判断
- 对多条规则做连续比较

缺少 session 记忆或结构化案件状态时，系统仍然是一个无状态 QA 端点。

## 3. 代码确认的具体缺口

下列问题不仅是从 README 文字推测得到的“可能风险”，而是当前实现确实存在的能力边界。

### 3.1 Planner 逻辑是启发式、关键词驱动

`app/agents/planner_agent.py` 主要依赖诸如 `and`、`or`、`compare`、`difference`、`what is` 等正则指示词模式。

影响包括：

- 对法律/规则文本的复杂表述可能更脆弱
- 子查询拆分大多是字符串切分
- 复杂合规问题可能被误判为 `direct`
- 多语言或混合表述的支持可能偏弱

### 3.2 Multi-hop 检索仍是“并集”合并，而非依赖感知

`app/retrieval/hybrid_retriever.py` 对每个子查询执行检索，再按分数合并。

这种方式简单稳定，但无法建模：

- 子问题之间的依赖关系
- 每个子查询的证据覆盖度
- 检索到的条款之间的冲突
- 分阶段检索（后续检索依赖前序发现）

### 3.3 二次检索未针对缺失证据定向

`app/agents/langgraph_workflow.py` 触发二次检索的依据是 planner 标志与迭代计数，而非第一轮检索后对证据覆盖度的评估。

影响包括：

- 二次检索可能重复
- 问题缺失的部分仍然缺失
- 图看起来是迭代的，但迭代尚未做到证据驱动

### 3.4 推理使用 top chunks，但未验证 chunk 使用

`app/agents/reasoning_agent.py` 用 top 检索结果构建上下文，并返回前几个 `used_chunk_ids`，但缺乏机制确保最终回答中的关键论断能与引用的 chunks 清晰对齐。

影响包括：

- 引用可能相关，但未必足够支撑全部论断
- 置信度估计偏弱
- 缺少“论断到证据”的结构化支持映射

### 3.5 工具系统只是占位

`app/tools/base_tool.py` 只定义了未来接口，但当前 graph 或 API 中没有工具调用路径。

影响包括：

- 不支持 calculator
- 不支持确定性的规则检查流程
- 不支持“检索 + 工具”融合工作流

## 4. 建议的优化方向

最有效的路径不是笼统地把系统做得“更 agentic”，而是增加能提升控制力、可追溯性、以及 HKEX 任务契合度的能力。

### 4.1 优先级 A：把 planner 强化为真正的执行控制器

当前状态：

- `direct` vs `multi_hop`
- 简单子查询切分
- 简单 `needs_second_retrieval`

建议升级：

- 增加更丰富的意图标签，例如：
- `rule_lookup`
- `obligation_summary`
- `comparison`
- `eligibility_or_threshold`
- `procedure_or_disclosure_flow`
- `calculation_required`
- 产出一个小型执行计划对象，而不是只有标签
- 在计划中附带字段，例如：
- `intent`
- `sub_tasks`
- `retrieval_strategy`
- `requires_tool`
- `evidence_requirements`
- `answer_format`

价值：

- 让 planner 从“分类”升级为“工作流控制”
- 后续检索、推理、工具使用可由显式 plan state 驱动

### 4.2 优先级 A：让二次检索变成证据驱动

与其只判断“要不要再检索一次”，系统更应该判断“第一轮检索后还缺什么”。

建议升级：

- 在第一轮检索后增加证据覆盖度检查
- 评估每个子任务是否至少有一条强支撑 chunk
- 若不足，仅针对未覆盖子任务启动定向检索
- 对模糊/信息不足的 query 可选用 query rewriting
- 记录检索追踪（trace）：每一轮为何发生

建议新增 state 字段：

- `sub_task_coverage`
- `missing_information`
- `retrieval_rounds`
- `query_rewrites`

价值：

- 让图的迭代变得“实质迭代”，而不是“形式迭代”。

### 4.3 优先级 A：在检索与推理之间增加证据选择/重排

当前架构从检索直接进入推理。

建议升级：

- 增加 `Evidence Selector` 或 `Reranker` 节点
- 去重高度重叠的 chunks
- 优先选择带明确 rule number、标题匹配的 chunks
- 保证证据多样性，避免单个长段落挤掉其它关键条款
- 可选：按子任务相关性评分，而非只按全局 query 相关性

价值：

- 合规回答往往需要“小而准”的证据集，而不是“大而噪”的上下文。

### 4.4 优先级 A：用支持检查约束答案生成

建议升级：

- 强制答案结构，例如：
- short answer
- supporting rules
- reasoning summary
- uncertainty / limitation note
- 对 multi-hop 问题逐个回答子任务
- 标记哪个 chunk 支撑哪个答案部分
- 证据不完整时明确避免输出不受支持的结论

更强版本：

- 在推理后加入轻量 verifier 节点
- verifier 检查每个主要论断是否被检索 chunks 支撑
- 支撑缺失则修订答案或降低置信度

价值：

- 想在不显著增加系统复杂度的前提下，提升 agentic 可信度，这是高性价比升级之一。

### 4.5 优先级 B：引入 HKEX 任务的工具使用

这是最清晰的 Phase 2 扩展方向。

建议优先工具：

- `SizeTestCalculatorTool`
- `RuleLookupTool`（按 rule number 的确定性检索/查找）
- `TransactionClassifierTool`（结构化事实输入）
- `DisclosureChecklistTool`（把义务转成清单）

建议路由方式：

- planner 决定 `requires_tool`
- graph 分支为 retrieval-only、tool-only、或 retrieval-plus-tool
- 最终回答融合：检索到的文本证据 + 工具的结构化输出

价值：

- 许多 HKEX 合规问题会因为“可计算/可清单化”的输出而更实用。

### 4.6 优先级 B：加入对话记忆与结构化案件上下文

建议升级：

- 支持基于 session 的 chat state
- 允许用户逐步补充交易事实
- 存储一个小型结构化 case 对象，例如：
- transaction type
- connected person status
- percentage ratios
- 已讨论的披露义务

价值：

- 真实合规工作流是迭代且事实依赖的
- 记忆能力让系统超越“一次性问答 demo”。

### 4.7 优先级 B：提升 query decomposition 质量

当前拆分主要基于连词切分。

建议升级：

- 按法律意图拆分，而非仅按语法
- 区分：
- 定义类子任务
- 阈值/门槛类子任务
- 例外/豁免类子任务
- 披露/程序类子任务
- 审批/股东批准类子任务
- 在 planner 输出中加入拆分依据

价值：

- 许多法律问题需要结构化拆解，但并不会显式出现 and/or 连接。

### 4.8 优先级 B：强化法律文本检索

建议升级：

- 基于元数据的过滤（chapter/section/rule number）
- 对 rule number 精确匹配做 boosting
- 支持缩写与同义词归一化
- 对法律术语进行可选 query rewriting
- 在进入 LLM 推理前加入简单法律重排启发式

价值：

- 法规语料对结构化检索控制的收益通常非常高。

### 4.9 优先级 C：加入评估与失败分析闭环

文档明确把完整 benchmark 与 RAGAS 推迟，这是合理的。但在 Phase 2 增加更多复杂度之前，至少需要轻量评估。

建议升级：

- 构建一个小的人工标注问题集
- 覆盖 `direct` 与 `multi_hop`
- 跟踪：检索 recall、引用质量、回答支撑质量
- 定义错误类别，例如：
- 检索到错误条款
- 漏检关键条款
- 条款正确但综合回答弱
- 过度自信的无支撑回答
- 本应使用工具

价值：

- 否则优化会变成“凭感觉”，缺少证据支撑。

### 4.10 优先级 C：增强 API 输出用于调试与前端

当前 response schema 已较结构化，这是优点。

建议新增字段：

- `execution_trace`
- `retrieval_rounds`
- `selected_evidence`
- `coverage_assessment`
- `confidence_level`
- `tool_calls`

价值：

- agentic 系统没有中间输出很难 debug
- 这些字段也能降低未来前端开发成本。

## 5. 建议路线图

为避免范围失控，下一轮不建议一次性加入全部内容。

### 阶段 1：让现有 graph 变得“更真实”

建议范围：

- 更丰富的 planner 输出
- 证据覆盖度检查
- 定向二次检索
- 证据选择或 reranker
- 更强的答案结构与不确定性纪律

预期结果：

- 系统仍保持小而可控
- 但 graph 将从“结构上 agentic”变为“行为上 agentic”。

### 阶段 2：加入 HKEX 专用工具

建议范围：

- size test calculator
- 确定性 rule lookup
- 结构化披露清单生成

预期结果：

- 系统开始覆盖纯 RAG 难以高质量解决的任务。

### 阶段 3：加入评估与记忆

建议范围：

- 小型 benchmark 集
- 失败分类体系
- session 记忆
- 结构化 case state

预期结果：

- 系统对迭代式合规场景更稳健。

## 6. 暂时不建议过度建设的内容

有些升级很诱人，但在上述基础能力稳定前，应继续保持 out-of-scope。

暂不建议：

- 大型多 agent 架构
- 带多次重试的自主循环
- 在没有可衡量收益前引入重框架复杂度
- 在基础评估缺失前就搭建生产级可观测性栈
- 在后端可追溯性不足前就投入大量 UI 开发

原因：

当前瓶颈不是缺复杂度，而是缺控制质量、证据纪律，以及面向领域任务的执行能力。

## 7. 最终结论

如果按“agentic 系统”的标准衡量，当前 Agentic RAG 功能确实偏单薄。

但从 Phase 1 的目标来看，这种单薄并不不合理，它是一个合格的最小可行原型。

真正的问题在于：当前实现仍更接近“带路由的 RAG”，而非更强的 “plan-retrieve-verify-act” 架构。

最有价值的下一步优化是：

1. 把 planner 强化为执行控制器
2. 让检索迭代由“缺失证据”驱动，而不是固定 flag
3. 在最终答案生成前加入证据选择与验证
4. 引入 HKEX 专用工具，特别是 size tests 与结构化合规任务
5. 加入轻量评估，让后续优化有明确方向

完成这些改动后，系统会从 Phase 1 的 Agentic RAG 演示，走向更可论证、也更实用的合规助手。
