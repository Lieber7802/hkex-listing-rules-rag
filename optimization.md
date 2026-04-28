# HKEX Agentic RAG Optimization Notes

> Scope: This document is based primarily on the project's Markdown documentation and supplemented by a limited review of the current agent, retrieval, and API code to verify whether the documented Agentic RAG capability is reflected in implementation.

## 1. Overall Judgment

The current Phase 1 system is a valid minimum viable Agentic RAG prototype, but its agentic capability is still thin.

This is not a criticism of Phase 1 scope. In fact, the current implementation is broadly consistent with the original Phase 1 goal in `README.md`, `README-zh.md`, and `spec.md`: build a small, local, testable backend with one planner step, hybrid retrieval, evidence-based answering, and citations.

However, if the question is whether the system is already "agentic enough" beyond a slightly enhanced single-shot RAG pipeline, the answer is: not yet.

The current system is closer to:

- Hybrid RAG
- plus a lightweight query classifier/router
- plus an optional extra retrieval pass

Rather than a stronger agentic system with explicit planning, execution, verification, and adaptive control.

## 2. Why It Feels Thin

### 2.1 The planner is still shallow

From the docs and code, the planner currently does three things:

- classify query as `direct` or `multi_hop`
- split some queries into simple sub-queries
- decide whether a second retrieval may be needed

This is useful, but still narrow. It does not yet:

- identify different intent categories beyond two labels
- produce a real execution plan
- reason about missing evidence explicitly
- select different retrieval strategies for different sub-tasks
- decide whether a tool should be used

In practice, this means the planner behaves more like a routing heuristic than a true planning component.

### 2.2 The second retrieval is not really an adaptive retrieval loop

The LangGraph workflow includes `Planner -> Retriever -> Conditional Router -> Second Retrieval -> Reasoning`, which is a good Phase 1 structure.

But based on `app/agents/langgraph_workflow.py`, the current second retrieval step mostly re-runs retrieval for the original query and appends unseen chunks. It does not yet:

- rewrite the query
- retrieve specifically for uncovered sub-questions
- check which parts of the question remain unsupported
- widen or narrow retrieval strategy dynamically
- stop based on evidence sufficiency rather than a fixed one-pass rule

So the graph structure is more advanced than the actual retrieval control policy.

### 2.3 The reasoning step synthesizes, but does not verify

The reasoning agent can generate an answer from retrieved evidence and attach citations. That is the correct Phase 1 baseline.

But based on `app/agents/reasoning_agent.py`, it does not yet enforce stronger evidence discipline such as:

- claim-to-citation alignment
- coverage checks for each sub-query
- contradiction detection across chunks
- answer revision when evidence is weak or incomplete
- explicit abstention when supporting evidence is missing

This makes the system citation-grounded in format, but not yet evidence-verified in behavior.

### 2.4 The system has no tool use yet

The docs explicitly reserve `app/tools/` for Phase 2, and `app/tools/base_tool.py` confirms that tool integration is only an interface stub.

That means the current system has no ability to:

- call a size test calculator
- run structured decision procedures
- invoke document lookup utilities selectively
- combine symbolic outputs with retrieved text evidence

For HKEX compliance scenarios, this is one of the biggest missing pieces, because many practical questions are not purely narrative retrieval problems.

### 2.5 There is no conversation memory or case state

The current API is essentially single-turn: one query in, one response out.

That is acceptable for Phase 1, but it limits the system for realistic compliance workflows where users may ask:

- follow-up clarification questions
- narrowing questions based on prior answers
- case-specific questions with accumulated facts
- comparisons across multiple rules in sequence

Without session memory or structured case state, the system remains a stateless QA endpoint.

## 3. Concrete Gaps Confirmed by Code

The following points are not just possible concerns inferred from README wording. They are supported by the current implementation.

### 3.1 Planner logic is heuristic and keyword-driven

`app/agents/planner_agent.py` relies mainly on regex indicators such as `and`, `or`, `compare`, `difference`, `what is`, and similar patterns.

Implications:

- classification may be brittle for legal phrasing
- sub-query decomposition is mostly string splitting
- complex compliance questions may be mislabeled as `direct`
- multilingual or mixed phrasing support is likely weak

### 3.2 Multi-hop retrieval is still union-based, not dependency-aware

`app/retrieval/hybrid_retriever.py` retrieves results for each sub-query and merges them by score.

This is simple and stable, but it does not model:

- dependency between sub-questions
- evidence coverage per sub-query
- conflicts between retrieved clauses
- staged retrieval where later retrieval depends on earlier findings

### 3.3 Second retrieval is not targeted by missing evidence

`app/agents/langgraph_workflow.py` triggers second retrieval based on planner flags and iteration count, not on actual evidence coverage after the first pass.

Implications:

- second retrieval may be redundant
- missing parts of the question may remain missing
- the graph looks iterative, but the iteration is not yet evidence-aware

### 3.4 Reasoning uses top chunks, not validated chunk usage

`app/agents/reasoning_agent.py` builds context from top retrieval results and returns the first few `used_chunk_ids`, but there is no strong mechanism ensuring that the final answer's statements map cleanly to the cited chunks.

Implications:

- citations may be relevant but not fully sufficient
- answer confidence is weakly estimated
- there is no structured support map between claims and evidence

### 3.5 Tool system is only a placeholder

`app/tools/base_tool.py` defines the future interface, but there is no execution path in the graph or API for tool invocation.

Implications:

- no calculator support
- no deterministic rule-based checks
- no hybrid retrieval-plus-tool workflow

## 4. Recommended Optimization Directions

The best path is not to make the system "more agentic" in a vague sense. The right approach is to add capabilities that improve control, traceability, and HKEX task fit.

### 4.1 Priority A: Strengthen the planner into a real execution controller

Current state:

- `direct` vs `multi_hop`
- simple sub-query splitting
- simple `needs_second_retrieval`

Recommended upgrade:

- add richer intent labels, for example:
- `rule_lookup`
- `obligation_summary`
- `comparison`
- `eligibility_or_threshold`
- `procedure_or_disclosure_flow`
- `calculation_required`
- generate a small execution plan object instead of only labels
- attach plan fields such as:
- `intent`
- `sub_tasks`
- `retrieval_strategy`
- `requires_tool`
- `evidence_requirements`
- `answer_format`

Why this matters:

- this turns the planner from classification into workflow control
- later retrieval, reasoning, and tool use can be driven by explicit plan state

### 4.2 Priority A: Make second retrieval evidence-aware

Instead of asking only whether a second retrieval should happen, the system should ask what is still missing after the first retrieval.

Recommended upgrade:

- add an evidence coverage check after first retrieval
- evaluate whether each sub-task has at least one strong supporting chunk
- if not, launch targeted retrieval for uncovered sub-tasks only
- optionally apply query rewriting for vague or underspecified questions
- keep a retrieval trace showing why each retrieval round happened

Suggested state additions:

- `sub_task_coverage`
- `missing_information`
- `retrieval_rounds`
- `query_rewrites`

Why this matters:

- the graph becomes meaningfully iterative rather than cosmetically iterative

### 4.3 Priority A: Add evidence selection or reranking between retrieval and reasoning

The current architecture goes from retrieval to reasoning quite directly.

Recommended upgrade:

- add an `Evidence Selector` or `Reranker` node
- deduplicate overlapping chunks
- prioritize chunks with explicit rule numbers and section matches
- preserve diversity so one long section does not crowd out other relevant clauses
- optionally score by sub-task relevance, not just global query relevance

Why this matters:

- compliance answers often need a small, precise evidence set rather than a larger noisy context

### 4.4 Priority A: Constrain answer generation with support checks

Recommended upgrade:

- require answer sections such as:
- short answer
- supporting rules
- reasoning summary
- uncertainty or limitation note
- for multi-hop questions, answer each sub-task explicitly
- mark which chunk supports which answer section
- if evidence is partial, explicitly abstain from unsupported claims

Stronger version:

- introduce a lightweight verifier node after reasoning
- verifier checks whether each major claim is supported by retrieved chunks
- if support is missing, revise answer or downgrade confidence

Why this matters:

- this is one of the most important upgrades if the project wants to claim stronger agentic behavior without becoming over-engineered

### 4.5 Priority B: Introduce tool use for HKEX-specific tasks

This is the clearest Phase 2 expansion point.

Recommended first tools:

- `SizeTestCalculatorTool`
- `RuleLookupTool` for deterministic lookup by rule number
- `TransactionClassifierTool` for structured fact inputs
- `DisclosureChecklistTool` that turns retrieved obligations into a checklist

Recommended routing logic:

- planner decides `requires_tool`
- graph branches into retrieval-only, tool-only, or retrieval-plus-tool paths
- final answer fuses retrieved textual evidence with structured tool outputs

Why this matters:

- many HKEX compliance questions become more useful when the system can combine rules with structured calculations or checklist outputs

### 4.6 Priority B: Add conversation memory and structured case context

Recommended upgrade:

- support session-based chat state
- allow users to provide transaction facts incrementally
- store a small structured case object, for example:
- transaction type
- connected person status
- percentage ratios
- disclosure obligations already discussed

Why this matters:

- real compliance workflows are iterative and fact-dependent
- memory makes the system more useful than a one-shot Q&A demo

### 4.7 Priority B: Expand query decomposition quality

Current decomposition is mostly based on splitting by conjunctions.

Recommended upgrade:

- decompose by legal intent, not grammar alone
- distinguish:
- definition sub-task
- threshold sub-task
- exception sub-task
- disclosure sub-task
- approval sub-task
- include decomposition rationale in planner output

Why this matters:

- legal questions often require structured decomposition that is not visible from sentence connectors alone

### 4.8 Priority B: Improve retrieval for legal text

Recommended upgrades:

- add metadata-aware filtering by chapter, section, or rule number
- support exact rule-number boosting
- support acronym and synonym normalization
- add optional query rewriting for legal terminology
- add simple legal reranking heuristics before LLM reasoning

Why this matters:

- legal and regulatory corpora benefit disproportionately from structure-aware retrieval controls

### 4.9 Priority C: Add evaluation and failure analysis loops

The docs explicitly defer full benchmark and RAGAS work, which is fine for Phase 1. But before Phase 2 adds more complexity, the project should add at least lightweight evaluation.

Recommended upgrade:

- create a small hand-labeled question set
- cover both `direct` and `multi_hop`
- track retrieval recall, citation quality, and answer support quality
- add error categories such as:
- wrong rule retrieved
- missing rule
- correct rule but weak synthesis
- overconfident unsupported answer
- tool should have been used

Why this matters:

- otherwise optimization becomes impression-driven rather than evidence-driven

### 4.10 Priority C: Improve API output for debugging and frontend use

The current response schema is already structured, which is good.

Recommended additions:

- `execution_trace`
- `retrieval_rounds`
- `selected_evidence`
- `coverage_assessment`
- `confidence_level`
- `tool_calls`

Why this matters:

- agentic systems are hard to debug without explicit intermediate outputs
- these fields also make a future frontend much easier to build

## 5. Suggested Roadmap

To keep scope under control, the next iteration should not add everything at once.

### Stage 1: Make the existing graph more real

Recommended scope:

- richer planner output
- evidence coverage check
- targeted second retrieval
- evidence selector or reranker
- stronger answer format with uncertainty discipline

Expected outcome:

- system remains small
- but the graph becomes meaningfully agentic rather than only structurally agentic

### Stage 2: Add HKEX-specific tools

Recommended scope:

- size test calculator
- deterministic rule lookup
- structured disclosure checklist generation

Expected outcome:

- system starts addressing tasks that plain RAG cannot solve well

### Stage 3: Add evaluation and memory

Recommended scope:

- small benchmark set
- failure taxonomy
- session memory
- structured case state

Expected outcome:

- system becomes more robust for iterative compliance use cases

## 6. What Should Not Be Overbuilt Yet

Some upgrades are tempting but should remain out of scope until the above items are stable.

Not recommended yet:

- large multi-agent architectures
- autonomous agent loops with many retries
- heavy framework complexity without measurable gain
- production observability stack before evaluation basics exist
- advanced UI work before backend traceability improves

Reason:

The current bottleneck is not missing complexity. It is missing control quality, evidence discipline, and domain-specific execution capability.

## 7. Final Conclusion

Yes, the current Agentic RAG functionality is somewhat thin if judged as an agentic system.

But it is not incorrectly thin for Phase 1. It is a reasonable minimum viable prototype.

The main issue is that the current implementation is still closer to "RAG with routing" than to a stronger "plan-retrieve-verify-act" architecture.

The most valuable next optimizations are:

1. strengthen the planner into an execution controller
2. make retrieval iterative based on missing evidence rather than fixed flags
3. add evidence selection and verification before final answer generation
4. introduce HKEX-specific tool use, especially for size tests and structured compliance tasks
5. add lightweight evaluation so future optimization has clear direction

If these changes are made, the system will move from a Phase 1 demonstration of Agentic RAG toward a more defensible and practically useful compliance assistant.
