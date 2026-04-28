# 1st Interim Report 大纲规划

> 项目：`Agentic RAG for HKEX Listing Rules Compliance`
> 
> 报告目标：围绕当前阶段研究进展，完成一份约 `15` 页的第一阶段中期报告。
> 
> 本大纲基于当前项目实际进度整理：Phase 1 后端原型已基本完成，包括文档导入、结构化切分、混合检索、LangGraph 编排、引用式问答、FastAPI 接口，以及对 Planner/证据链路的进一步优化思考。

---

## 1. 报告定位

这份 1st Interim Report 不应该写成“最终成果展示”，而应该写成：

- 一个**研究驱动的系统设计与阶段性实现报告**
- 强调：
  - 选题背景与问题价值
  - 与现有方案的关系
  - 你当前已经完成了什么
  - 你的系统为什么这样设计
  - 初步实验说明系统是否可行
  - 下一阶段准备如何补全和优化

换句话说，这份报告的重点不是“我写完了多少代码”，而是：

- 为什么这个问题值得做
- 为什么 Agentic RAG 比普通 RAG 更适合这个场景
- 目前实现的原型已经验证了哪些关键假设
- 还有哪些问题尚未解决

---

## 2. 推荐格式

### 2.1 首选建议

如果课程没有提供固定模板，建议采用：

- **单栏 academic project report 格式**
- 章节编号使用：`1, 1.1, 1.2 ...`
- 引文格式使用：`IEEE 引用风格`（文中 `[1] [2] [3]`，文末编号参考文献）

### 2.2 页面与排版建议

- 纸张：`A4`
- 页边距：`2.54 cm` 左右
- 字体：
  - 正文：`Times New Roman 12pt`
  - 若中文为主：可用 `宋体/Times New Roman` 混排，但需统一
- 行距：`1.5 倍` 或 `固定 20-22 pt`
- 对齐：两端对齐
- 图片与表格：居中，带编号与标题
- 页码：页脚居中或右下角

### 2.3 为什么不推荐直接用 IEEE 双栏模板

虽然这是计算机领域常见格式，但这次报告要求是“15 页中期报告”，不是 conference paper。双栏格式会导致：

- 内容显得过密
- 系统结构图和流程图不易展示
- 项目进度、方法细节、里程碑部分可读性变差

因此更推荐：

- **结构参考 IEEE 的章节组织方式**
- **版式使用单栏课程项目报告格式**

一句话建议：

- **参考 IEEE 的写法，不强制照搬 IEEE 双栏模板**

---

## 3. 总体页数与字数预算

### 3.1 总体估算

如果采用单栏、12pt、1.5 倍行距：

- `15 页` 报告大约对应：
  - 英文：`4500 - 6000` 词
  - 中文：约 `7000 - 9500` 字

建议按 `8000 字左右` 控制正文，参考文献单独计入总页数。

### 3.2 页数分配建议

| 章节 | 建议页数 | 建议字数 | 说明 |
|---|---:|---:|---|
| 1. Introduction | 1.5 - 2 页 | 800 - 1200 字 | 背景、目标、意义、预期成果 |
| 2. Related Work | 2 - 2.5 页 | 1200 - 1600 字 | 现有方案、优缺点、对比 |
| 3. System Modeling and Structure | 2.5 - 3 页 | 1400 - 1800 字 | 系统架构、模块设计、流程图 |
| 4. Methodology and Algorithms | 3 - 3.5 页 | 1700 - 2200 字 | 方法与算法细节，是核心部分 |
| 5. Preliminary Experiments | 2 - 2.5 页 | 1000 - 1400 字 | 初步实验、案例分析、当前结果 |
| 6. Milestones and Schedule | 1 - 1.5 页 | 500 - 800 字 | 里程碑、时间安排 |
| 7. Work for Next Report | 0.8 - 1 页 | 400 - 700 字 | 下一阶段工作 |
| 8. References | 1 - 1.5 页 | 不限 | 预计 12 - 20 条参考文献 |

总计：约 `15 页`

---

## 4. 推荐章节结构

以下结构与老师要求一一对应，同时也适配你当前项目进度。

---

## 5. 正式大纲

## 1. Introduction

### 建议页数

- `1.5 - 2 页`

### 建议小节数

- `3` 个小节

### 建议结构

#### 1.1 Background and Problem Context

应写内容：

- HKEX Listing Rules 合规问答的现实背景
- 上市规则文档复杂、章节多、交叉引用强
- 合规判断需要快速定位条款与解释性材料
- 人工查阅成本高、效率低、容易遗漏关联条款

可强调的问题：

- 法规文本长、结构复杂
- 用户问题既有直接条款查询，也有多条规则整合问题
- 传统 keyword search 或普通 QA 难以稳定支持引用式回答

#### 1.2 Project Objectives

应写内容：

- 本项目目标是实现一个面向 HKEX 上市规则合规问答的 Agentic RAG 原型系统
- 当前阶段目标：
  - 完成后端原型
  - 跑通知识库处理链路
  - 实现基础 Agentic RAG 编排
  - 输出带引用的回答

建议明确“第一阶段不做什么”：

- 不做前端
- 不做 calculator tool
- 不做 benchmark 全量评测
- 不做生产级部署

#### 1.3 Practical Value and Expected Outcome

应写内容：

- 项目实用性：支持规则定位、合规辅助问答、披露要求理解
- 预期成果：
  - 一个可运行的后端软件原型
  - 一套结构化知识处理与检索流程
  - 初步实验结果
  - 为后续工具化和评测预留接口

### 建议字数

- `900 - 1200 字`

---

## 2. Related Work

### 建议页数

- `2 - 2.5 页`

### 建议小节数

- `4` 个小节

### 建议结构

#### 2.1 Traditional Information Retrieval for Regulatory Documents

应写内容：

- 传统关键词检索、BM25、规则库搜索
- 优点：稳定、快、可解释
- 缺点：缺乏语义理解、难以回答多跳问题

#### 2.2 Neural Retrieval and Dense Retrieval

应写内容：

- Dense embedding、向量检索、语义匹配
- 优点：语义召回更强
- 缺点：可能检索到语义相近但法律上不精确的内容

#### 2.3 RAG and Agentic RAG Systems

应写内容：

- 普通 RAG：单轮检索 + 生成
- Agentic RAG：加入 planning/routing、多轮检索、证据控制
- 说明为什么你的项目选择 Agentic RAG，而不是纯生成式 QA

#### 2.4 Relationship Between Existing Solutions and the Proposed Solution

应写内容：

- 你的系统如何结合传统 BM25 与 dense retrieval
- 你的系统相比普通 RAG 多了哪些 agentic 元素：
  - planner/router
  - 多条证据整合
  - 条件二次检索
  - citation-grounded answer
- 也要诚实指出当前限制：
  - 仍是 MVP
  - planner 还不够强
  - 暂无 tool/memory/evaluation

### 建议字数

- `1200 - 1600 字`

### 建议参考文献数量

- `4 - 6` 篇/类来源

---

## 3. System Modeling and Structure

### 建议页数

- `2.5 - 3 页`

### 建议小节数

- `4` 个小节

### 建议结构

#### 3.1 Problem Scope and System Boundary

应写内容：

- 只聚焦 HKEX 相关规则的局部范围：
  - Notifiable Transactions
  - Connected Transactions
  - Size Tests 相关章节
  - disclosure / reporting obligations
- 输入输出边界：
  - 输入：自然语言合规问题
  - 输出：回答 + 引用 + 检索证据

#### 3.2 Overall Architecture

应写内容：

- 系统总体模块图
- 建议放图：
  - `Document Ingestion -> Chunking -> Indexing -> Planner -> Retriever -> Reasoning -> Citation`

#### 3.3 LangGraph Workflow Structure

应写内容：

- 当前实际工作流：
  - Planner
  - Retriever
  - Conditional Router
  - Second Retrieval
  - Reasoning
- 若你想体现最新进展，也可以补一句：
  - 已进一步探索更强的 planner / validation / decomposition 方案，作为后续扩展基础

#### 3.4 Design Justifications

应写内容：

- 为什么使用 structure-aware chunking
- 为什么采用 hybrid retrieval
- 为什么采用 LangGraph 而不是写死脚本流程
- 为什么当前只做轻量 agentic，而不做复杂多 agent

### 建议字数

- `1400 - 1800 字`

### 建议配图

- `1 - 2` 张结构图/流程图

---

## 4. Methodology and Algorithms

### 建议页数

- `3 - 3.5 页`

### 建议小节数

- `5` 个小节

### 建议结构

#### 4.1 Knowledge Base Construction Pipeline

应写内容：

- 文档导入
- 文本清洗
- 中间产物保存
- PDF / txt / md 的处理思路

#### 4.2 Structure-Aware Chunking Algorithm

应写内容：

- 为什么不能粗暴按 token 切块
- 如何尽量保留：
  - chapter
  - section title
  - rule number
  - source path
- chunk 元数据字段设计

#### 4.3 Hybrid Retrieval Strategy

应写内容：

- BM25 检索
- dense retrieval
- score fusion / 合并策略
- 为什么 hybrid retrieval 对规则文本更稳

#### 4.4 Agentic Workflow: Planning, Retrieval and Reasoning

应写内容：

- planner 如何进行 direct / multi-hop 基础判断
- 二次检索如何被触发
- reasoning agent 如何整合多条证据
- citation formatter 如何生成可追溯引用

#### 4.5 Current Limitations and Planned Algorithmic Enhancements

应写内容：

- 当前 planner 仍偏启发式
- 当前二次检索仍偏简单
- 当前推理缺少更强验证
- 引出下一阶段：
  - stronger planner
  - evidence coverage checking
  - tool integration
  - evaluation benchmark

### 建议字数

- `1700 - 2200 字`

### 建议配图/表

- `1` 张流程图
- `1` 张算法或模块说明表

---

## 5. Preliminary Performance Analysis or Experiments

### 建议页数

- `2 - 2.5 页`

### 建议小节数

- `4` 个小节

### 建议结构

#### 5.1 Experimental Setup

应写内容：

- 开发环境
- 模型配置：
  - DeepSeek Reasoner
  - BGE-M3 via Ollama
- 向量库：FAISS
- 检索组件：BM25 + dense

#### 5.2 Functional Verification

应写内容：

- 验证 ingestion 正常
- 验证 chunk/index 构建正常
- 验证 API 返回正常
- 验证 citations 可追溯

#### 5.3 Preliminary Query Case Study

应写内容：

- 给出 `2 - 4` 个示例问题
- 包括：
  - direct clause retrieval
  - basic multi-hop question
- 展示：
  - query
  - retrieved rule/chunk
  - answer
  - citation

#### 5.4 Preliminary Analysis

应写内容：

- 当前系统在哪些问题上表现较好
- 当前问题：
  - planner 偏简单
  - 二次检索不足够自适应
  - 证据验证有限
- 强调：当前实验是可行性验证，不是完整 benchmark

### 建议字数

- `1000 - 1400 字`

### 建议表格

- `1` 张实验案例表
- `1` 张当前系统优缺点总结表

---

## 6. Milestones and Overall Schedule

### 建议页数

- `1 - 1.5 页`

### 建议小节数

- `2` 个小节

### 建议结构

#### 6.1 Work Completed So Far

应写内容：

- 已完成：
  - 项目骨架
  - 配置系统
  - ingestion pipeline
  - cleaner + chunker
  - BM25 + FAISS
  - hybrid retrieval
  - planner + reasoning
  - FastAPI 接口
  - 单元测试
  - README 文档

#### 6.2 Project Schedule and Milestones

应写内容：

- 用表格或时间线说明：
  - Phase 1 已完成内容
  - Phase 2 预期任务
  - Final report 前的节点

### 建议字数

- `500 - 800 字`

### 建议表格

- `1` 张 milestone 表

---

## 7. Work to be Completed for the Next Report

### 建议页数

- `0.8 - 1 页`

### 建议小节数

- `2` 个小节

### 建议结构

#### 7.1 Technical Improvements

应写内容：

- planner 增强
- evidence coverage / verifier
- tool interface 进一步落地
- query decomposition / routing 优化
- 更好的 retrieval evaluation

#### 7.2 Evaluation and Reporting Work

应写内容：

- 构建 benchmark / 测试问题集
- 做更系统的实验
- 与 baseline 对比
- 整理最终系统演示与结果分析

### 建议字数

- `400 - 700 字`

---

## 8. References

### 建议页数

- `1 - 1.5 页`

### 建议条目数

- `12 - 20` 条

### 参考来源建议

- RAG / Agentic RAG 论文
- dense retrieval / BM25 / hybrid retrieval 论文
- LangGraph / LangChain 官方文档
- HKEX 官方规则与 guidance 页面
- DeepSeek / BGE-M3 / FAISS 等技术资料

---

## 6. 推荐的最终目录形式

你可以直接按下面这个目录写报告：

```text
Title
Abstract (可选，半页以内)

1. Introduction
  1.1 Background and Problem Context
  1.2 Project Objectives
  1.3 Practical Value and Expected Outcome

2. Related Work
  2.1 Traditional Information Retrieval for Regulatory Documents
  2.2 Neural and Dense Retrieval Methods
  2.3 RAG and Agentic RAG Systems
  2.4 Relationship Between Existing Work and This Project

3. System Modeling and Structure
  3.1 Problem Scope and System Boundary
  3.2 Overall Architecture
  3.3 LangGraph Workflow Structure
  3.4 Design Justifications

4. Methodology and Algorithms
  4.1 Knowledge Base Construction Pipeline
  4.2 Structure-Aware Chunking Algorithm
  4.3 Hybrid Retrieval Strategy
  4.4 Agentic Workflow: Planning, Retrieval and Reasoning
  4.5 Current Limitations and Planned Enhancements

5. Preliminary Performance Analysis or Experiments
  5.1 Experimental Setup
  5.2 Functional Verification
  5.3 Preliminary Query Case Study
  5.4 Preliminary Analysis

6. Milestones and Overall Schedule
  6.1 Work Completed So Far
  6.2 Project Schedule and Milestones

7. Work to be Completed for the Next Report
  7.1 Technical Improvements
  7.2 Evaluation and Reporting Work

8. References
```

---

## 7. 写作顺序建议

建议不要从 Introduction 开始写，而是按下面顺序写：

1. `Section 3 System Modeling and Structure`
2. `Section 4 Methodology and Algorithms`
3. `Section 5 Preliminary Experiments`
4. `Section 6 Milestones`
5. `Section 7 Next Work`
6. `Section 2 Related Work`
7. `Section 1 Introduction`
8. `References`

原因：

- 你现在最清楚的是“系统做了什么”
- Introduction 和 Related Work 反而适合最后回过头来写

---

## 8. 最终建议

这份 1st Interim Report 最适合采用的策略是：

- **报告主线聚焦 Phase 1 已完成的 MVP 原型**
- **实验部分强调可行性验证，而不是追求高强度 benchmark**
- **在方法和系统设计中适当引出当前不足与后续优化方向**

最重要的是，不要把报告写成“功能列表说明书”，而要写成：

- 问题背景
- 方法选择
- 系统结构
- 初步验证
- 下一步计划

这样最符合中期报告的学术风格和老师给的要求。
