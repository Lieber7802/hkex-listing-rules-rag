# Evaluation Module Implementation Plan

Project: HKEX Listing Rules Compliance Agentic RAG System

This document is the implementation reference for the final evaluation module. The validation foundation is further specified in `docs/evaluation-validation-remediation-plan.md`; where older examples conflict with that document or the strict schemas in `app/evaluation/`, the remediation contract takes precedence.

## 1. Evaluation Goal

The evaluation module measures whether the complete Agentic RAG system improves HKEX compliance question answering over a traditional non-agentic RAG baseline.

The evaluation is for the final thesis/report. It is an offline research evaluation module, not a frontend or production-monitoring feature.

Core research questions:

| ID | Research question | Evidence required |
|---|---|---|
| RQ1 | Does Agentic RAG improve answer quality over Traditional Hybrid RAG? | RAGAS-compatible answer and retrieval metrics |
| RQ2 | Does the agentic workflow improve compliance-specific tasks? | route, tool, citation, multi-turn, negative-case metrics |
| RQ3 | Is the system robust across language, difficulty, and task type? | breakdown by language, difficulty, category, and negative cases |

## 2. Fixed Evaluation Decisions

These decisions are fixed for the evaluation implementation.

| Decision area | Final decision |
|---|---|
| Systems compared | Traditional Hybrid RAG vs Agentic RAG |
| Frontend evaluation | Not evaluated |
| LLM comparison | Not evaluated |
| Evaluated-system LLM | DeepSeek V4 Flash for both systems |
| Benchmark style | Source-grounded LLM-assisted benchmark |
| Main benchmark size | 300 cases |
| Candidate generation size | 500-700 cases before filtering |
| Language ratio | English 70%, Chinese 30% |
| Gold annotation | Structured Gold Annotation with deterministic checks, an independent judge, and recorded human approval |
| Difficulty levels | Easy, Medium, Hard |
| Multi-turn cases | Included |
| Negative cases | Included |
| Main metric family | RAGAS-compatible RAG metrics plus project-specific agent/citation/tool metrics |
| Main source eligibility | Current, active sources from a frozen corpus snapshot |
| Archive sources | Historical/noise stress cases only; never current-rules gold evidence |
| Sampling | Fixed-seed sampling from explicit category x language x difficulty cells |
| Statistical comparison | Paired case comparison with confidence intervals |

## 3. Evaluated Systems

### 3.1 Traditional Hybrid RAG

Traditional Hybrid RAG is the non-agentic baseline. It uses the same knowledge base, embedding model, BM25 index, vector index, RRF fusion strategy, and answer-generation LLM as Agentic RAG.

It must not use:

- planner/intent routing
- tool calls
- tool input extraction
- tool chain
- coverage checker
- evidence selector
- answer verifier
- contextual query rewriter

Traditional Hybrid RAG behavior:

1. Receive query.
2. Run one-pass hybrid retrieval through BM25 + dense retrieval + RRF.
3. Use top retrieved chunks as context.
4. Generate an answer with DeepSeek V4 Flash.
5. Return answer, retrieved chunks, citations derived from the top retrieved chunks, latency, and errors.

For multi-turn cases, the baseline may include previous turns in the answer-generation prompt, but retrieval must use only the current user query. This keeps it a traditional conversational RAG baseline without agentic query rewriting.

### 3.2 Agentic RAG

Agentic RAG is the complete current project system.

It includes:

- LLM-primary intent planner with deterministic heuristic fallback
- intent and route decision
- hybrid retrieval
- coverage checker
- evidence selector
- reasoning agent
- answer verifier
- tool input extraction
- tool execution
- tool chain
- multi-turn session context

Agentic RAG should be executed through the current orchestrator in `app/agents/agentic_workflow.py`.

### 3.3 Why Vector-Only RAG Is Not a Main Baseline

Vector-only RAG is not part of the main comparison. The thesis goal is to evaluate whether agentic abilities improve a strong traditional RAG system, not to compare retrieval algorithms.

If time permits, Vector-only RAG may be added as an appendix ablation, but it must not distract from the main experiment.

## 4. Benchmark Design

### 4.1 Main Benchmark Size

The main benchmark contains 300 cases.

The system should generate 500-700 candidate cases, validate them automatically, then select 300 high-quality cases for the main benchmark.

Additional valid cases may be saved as reserve or stress cases.

Recommended output sets:

| Dataset split | Size | Purpose |
|---|---:|---|
| Main benchmark | 300 | Main thesis experiment |
| Stress benchmark | 100 | Hard, negative, multi-hop, or robustness-focused cases |
| Reserve benchmark | 100-200 | Backup cases, optional additional checks |

### 4.2 Main Benchmark Distribution

The 300-case main benchmark should follow this distribution.

| Category | Count | Purpose |
|---|---:|---|
| Rule lookup | 50 | Direct high-frequency rule lookup |
| Obligation / disclosure summary | 50 | Disclosure and obligation synthesis |
| Procedure / compliance flow | 40 | Step-by-step compliance requirements |
| Comparison / multi-hop | 45 | Cross-rule or cross-document reasoning |
| Size test calculation | 40 | Tool calculation ability |
| Tool chain cases | 30 | size test -> classifier -> checklist |
| Multi-turn follow-up | 25 | Context-dependent follow-up questions |
| Negative / insufficient information | 20 | hallucination control and uncertainty handling |
| Total | 300 |  |

Language distribution:

| Language | Count |
|---|---:|
| English | 210 |
| Chinese | 90 |

The language split is cross-cutting. Chinese cases should appear across rule lookup, obligation summary, procedure, multi-hop, tool, multi-turn, and negative categories.

Difficulty distribution:

| Difficulty | Count | Definition |
|---|---:|---|
| Easy | 105 | Single rule, direct query, no tool |
| Medium | 135 | Multiple evidence chunks, paraphrase, complete tool inputs |
| Hard | 60 | Multi-hop, cross-rule comparison, context-dependent follow-up, missing parameters, or negative case; language alone does not determine difficulty |

### 4.3 Structured Gold Annotation Schema

Each benchmark case must validate against `app.evaluation.schemas.BenchmarkCase`.
The schema uses an explicit `case_type`: `answerable`, `tool`, `multi_turn`, or
`negative`. Category is not overloaded with intent or capabilities:

- `primary_category` is the mutually exclusive reporting category;
- `capability_tags` are cross-cutting labels such as `chinese`, `multi_hop`,
  `tool_chain`, `context_dependent`, or `negative`;
- `expected_intent` uses the exact planner intent vocabulary;
- `expected_route` uses `retrieval`, `tool_only`, or `tool_plus_retrieval`.

Source-backed answer points must map to exact chunks and ruleset-aware rule
references. Tool-backed points map to ordered expected tool calls.

```json
{
  "case_id": "case_001",
  "case_type": "answerable",
  "query": "What are the disclosure requirements for a major transaction?",
  "language": "en",
  "primary_category": "obligation_summary",
  "capability_tags": ["multi_evidence"],
  "difficulty": "medium",
  "as_of": "2026-07-11",
  "expected_intent": "obligation_summary",
  "expected_route": "retrieval",
  "answer_points": [
    {
      "point_id": "announcement",
      "text": "The issuer must publish an announcement",
      "evidence_kind": "source",
      "supporting_chunk_ids": ["chunk_abc"],
      "supporting_rules": [
        {
          "ruleset": "main_board",
          "rule_number": "14.34",
          "supporting_chunk_ids": ["chunk_abc"]
        }
      ],
      "required": true
    }
  ],
  "expected_rules": [
    {
      "ruleset": "main_board",
      "rule_number": "14.34",
      "supporting_chunk_ids": ["chunk_abc"]
    }
  ],
  "expected_tool_calls": [],
  "source_chunk_ids": ["chunk_abc"],
  "provenance": {
    "generator_model": "generator-model",
    "generator_prompt_hash": "<64 lowercase hex characters>",
    "source_snapshot_id": "snapshot-...",
    "source_snapshot_hash": "<64 lowercase hex characters>"
  }
}
```

Tool cases add ordered `expected_tool_calls`, including full inputs, partial or
full expected outputs, and numeric tolerances. Multi-turn cases store the same
intent, route, answer-point, tool, and negative expectations inside each turn.
Negative cases use a structured `negative_expectation` with reason, expected
action, missing inputs, and expected message points.

## 5. Source Graph Design

The source graph is required for high-quality multi-hop, tool-chain, multi-turn, and negative-case generation.

The source graph connects related HKEX chunks before benchmark generation. The generator then receives a small connected subgraph instead of random isolated chunks.

### 5.1 Source Graph Inputs

Primary input:

```text
data/indexes/vector/chunks.json
```

Fallback input:

```text
data/chunks/*.json
```

Optional semantic input:

```text
data/indexes/vector/faiss_index.bin
data/indexes/vector/chunk_ids.pkl
```

If the vector index is available, semantic similarity edges should be generated from existing FAISS vectors. Do not re-embed all chunks unless the vector index is unavailable and the user explicitly requests it.

### 5.2 Source Eligibility And Canonicalization

Before graph construction, run `scripts/build_evaluation_snapshot.py`. It creates
a frozen source registry and applies these fail-closed rules:

- `active` sources may support the current-rules main benchmark;
- `archived`, `withdrawn`, and `superseded` sources are stress-only;
- `unknown` status is ineligible until explicitly resolved;
- exact normalized-text duplicates point to one canonical chunk;
- snapshot date must fall inside any known effective-date interval;
- short or empty fragments are ineligible as standalone gold evidence.

The source registry preserves `ruleset` (`main_board`, `gem`, or `guidance`),
status, snapshot date, effective dates, content hashes, duplicate lineage,
eligibility flags, and exclusion reasons. Main Board/GEM identity must never be
discarded during rule-number normalization.

### 5.3 Node Schema

Each chunk is one graph node.

```json
{
  "node_id": "chunk:main_board_14_34_001",
  "chunk_id": "main_board_14_34_001",
  "document_id": "main_board",
  "source_path": "data/raw/rules/main_board.pdf",
  "doc_type": "rule",
  "ruleset": "main_board",
  "rule_number": "14.34",
  "source_status": "active",
  "snapshot_date": "2026-07-11",
  "canonical_text_hash": "...",
  "duplicate_of": null,
  "eligible_main_benchmark": true,
  "chapter": "14",
  "section_title": "Notification and announcement",
  "language": "en",
  "text": "...",
  "keywords": ["major transaction", "announcement", "shareholder approval"],
  "scenarios": ["notifiable_transaction", "disclosure_obligation"]
}
```

`doc_type` should be derived from source path and filename:

| Source pattern | doc_type |
|---|---|
| `data/raw/rules/` | `rule` |
| `guidance_letters` | `guidance_letter` |
| `listing_decisions` | `listing_decision` |
| `faqs` | `faq` |
| `review_committee_decisions` | `review_decision` |
| `enforcement_guidance` | `enforcement` |
| `forms_templates` | `form_template` |
| otherwise | `other` |

### 5.4 Domain Scenarios

Each node should be tagged with zero or more scenarios.

Initial scenario vocabulary:

| Scenario | Keywords |
|---|---|
| `connected_transaction` | connected transaction, connected person, Chapter 14A, associate |
| `notifiable_transaction` | notifiable transaction, Chapter 14, percentage ratio |
| `major_transaction` | major transaction, very substantial acquisition, very substantial disposal |
| `disclosure_obligation` | announcement, disclose, disclosure, circular |
| `shareholder_approval` | shareholder approval, independent shareholders, vote, meeting |
| `size_test` | size test, percentage ratio, assets ratio, consideration ratio |
| `listing_eligibility` | listing applicant, market capitalization, profit test, eligibility |
| `exemption` | exemption, waiver, de minimis |
| `procedure_flow` | procedure, application, submit, process, steps |

Chinese keywords should also be included where useful:

```text
关连交易, 关联交易, 披露, 公告, 通函, 股东批准, 豁免, 百分比率, 主要交易, 上市资格
```

### 5.5 Edge Schema

```json
{
  "src": "chunk:main_board_14_06",
  "dst": "chunk:main_board_14_34",
  "edge_type": "same_scenario",
  "weight": 0.78,
  "reason": "Both chunks discuss notifiable transaction classification and announcement obligations.",
  "evidence": ["notifiable transaction", "announcement"]
}
```

### 5.6 Edge Types

The source graph must include these edge types.

| Edge type | Rule | Weight |
|---|---|---:|
| `same_rule` | same normalized rule number | 1.00 |
| `rule_reference` | source text explicitly cites destination rule | 0.95 |
| `tool_dependency` | size test -> classification -> checklist relation | 0.90 |
| `semantic_similarity` | existing vector similarity above threshold | 0.60-0.85 |
| `same_scenario` | shared scenario tags | 0.70 |
| `same_section` | same normalized section title | 0.55 |
| `same_chapter` | same chapter | 0.40 |
| `keyword_overlap` | shared domain keywords | 0.40-0.70 |

### 5.7 Rule Reference Extraction

Use regex to extract explicit rule/chapter references.

Required English patterns:

```text
Rule 14.34
Rules 14.33 and 14.34
Chapter 14A
Main Board Rule 14A.35
GEM Rule 19.06
```

Required Chinese patterns:

```text
第14A.35条
规则14.34
第十四章
第14A章
```

Normalize extracted rule numbers before lookup:

- remove `Rule` and `Rules` from the display value
- store `Main Board` or `GEM` as the separate `ruleset` identity
- normalize whitespace
- preserve chapter letters such as `14A`
- preserve decimal suffixes such as `14A.35`

### 5.8 Semantic Similarity Edges

If FAISS vectors are available:

1. Load vector index.
2. Reconstruct stored vectors from the FAISS index.
3. For each node, find top similar nodes.
4. Exclude itself.
5. Keep only edges above threshold.

Recommended parameters:

```text
top_k = 10
similarity_threshold = 0.72
max_semantic_edges_per_node = 5
```

Semantic edges should be undirected logically, but may be stored as two directed edges if that simplifies implementation.

### 5.9 Source Graph Outputs

Write graph artifacts to:

```text
data/evaluation/source_graph/
  nodes.jsonl
  edges.jsonl
  graph_stats.json
```

`graph_stats.json` should include:

```json
{
  "node_count": 38765,
  "edge_count": 120000,
  "edge_type_counts": {
    "same_rule": 1000,
    "rule_reference": 5000
  },
  "scenario_counts": {
    "connected_transaction": 3000
  },
  "created_at": "2026-07-09T00:00:00Z"
}
```

## 6. Benchmark Generation Pipeline

### 6.1 Candidate Generation

Generate 500-700 candidate cases from source graph samples.

Generation patterns:

| Pattern | Source graph sample | Target cases |
|---|---|---|
| single rule | one high-quality rule node | rule lookup |
| rule + obligation | connected rule and disclosure node | obligation summary |
| procedure chain | same scenario + procedure nodes | procedure flow |
| rule + exemption | general rule and exemption rule | exemption questions |
| classification + disclosure | size/classification/disclosure nodes | tool and tool-chain cases |
| guidance + rule | guidance node and referenced rule node | multi-hop explanation |
| Main Board + GEM or similar sections | related rule nodes | comparison |
| connected subgraph of 2-3 nodes | high-weight edges | multi-hop |
| first broad turn + follow-up | same connected subgraph | multi-turn |
| unsupported or incomplete prompt | no matching rule or missing tool inputs | negative cases |

### 6.2 Multi-Hop Generation

Multi-hop questions must be generated from connected subgraphs, not random chunks.

Valid multi-hop subgraphs:

- 2 or 3 nodes
- at least one edge type in `rule_reference`, `same_scenario`, `semantic_similarity`, or `tool_dependency`
- combined source text under prompt limit
- source nodes not all from the same rule chunk

Example:

```text
Source A: percentage ratio / size test rule
Source B: classification threshold rule
Source C: announcement or circular obligation rule
```

Generated case:

```text
A listed issuer proposes an acquisition with a highest percentage ratio of 30%.
How should the transaction be classified and what disclosure obligation applies?
```

### 6.3 Chinese Case Generation

Chinese cases should be generated directly from source passages. Do not rely only on translating English cases.

Chinese cases should include:

- Chinese natural-language compliance questions
- mixed Chinese-English rule references
- Chinese tool queries with HKD amounts
- Chinese follow-up questions

### 6.4 Negative Case Generation

Negative cases should be 20 cases in the main benchmark.

Negative case types:

| Type | Example | Expected behavior |
|---|---|---|
| nonexistent rule | What is Rule 99Z.999? | say not found / insufficient evidence |
| insufficient tool inputs | Calculate the size test for a HKD 100m deal | ask for missing parameters or explain limitation |
| ambiguous query | What approvals are needed? | state ambiguity or ask for context |
| out-of-scope query | What is US SEC Rule 144? | indicate outside HKEX scope |
| false premise | Does Rule 14A.35 eliminate all disclosure obligations? | correct the premise using evidence |

## 7. Benchmark Validation Pipeline

Each generated candidate must be validated before entering the main benchmark.

Validation is layered. No LLM-only path may set `accepted=true`.

1. Strict schema validation rejects inconsistent case types and fields.
2. Deterministic validation checks source eligibility, per-point mappings,
   ruleset-aware rule references, language, duplicate risk, and reproducible tool
   inputs/outputs.
3. A blind judge model, different from the generator model, returns the structured
   rubric in `JudgeAssessment`.
4. At least one human reviewer approves source and rule correctness.

Judge support results may cite only the chunks mapped to that answer point.
Human approval records explicit per-dimension decisions and every reviewed chunk
ID; a source-backed approval that omits any case evidence chunk is invalid.

The judge uses this fixed 1-5 rubric:

| Score | Meaning |
|---:|---|
| 1 | unsupported or materially incorrect |
| 2 | major gaps or weak fit |
| 3 | partially correct but requires revision |
| 4 | supported and acceptable with only minor issues |
| 5 | fully supported, precise, and unambiguous |

Applicable judge dimensions must score at least 4. Every required answer point
must have an explicit support result. `null` is allowed only for a genuinely
non-applicable dimension, such as source support for an out-of-scope negative
case.

Negative cases use type-specific profiles rather than the answerable-case source
rule. Nonexistent-rule and out-of-scope cases do not require supporting chunks;
false-premise cases require corrective evidence; insufficient-tool-input cases
must name the target tool and demonstrate that declared inputs are actually
missing.

`ValidationRecord.accepted` is derived from check statuses and human reviews. It
is not trusted as input. The accepted pool is then sampled with explicit joint
category x language x difficulty quotas and a fixed seed. All rejected and
pending records remain in `benchmark_validation.jsonl`.

## 8. Metrics

The evaluation combines RAGAS-compatible metrics and project-specific metrics.

### 8.1 Retrieval Metrics

| Metric | Definition | Systems |
|---|---|---|
| Context Precision | Relevant retrieved contexts ranked higher than irrelevant contexts | both |
| Context Recall | Gold evidence covered by retrieved contexts | both |
| Hit@5 | any expected rule appears in top 5 retrieved chunks | both |
| Hit@10 | any expected rule appears in top 10 retrieved chunks | both |
| MRR | reciprocal rank of first expected rule match | both |

### 8.2 Citation Metrics

| Metric | Definition | Systems |
|---|---|---|
| Citation Hit Rate | final citations include at least one expected rule/source | both |
| Citation Support Score | cited chunks support answer points, judged by LLM | both |

### 8.3 Answer Metrics

| Metric | Definition | Systems |
|---|---|---|
| Faithfulness | answer claims are supported by retrieved/cited evidence | both |
| Response Relevancy | answer addresses the user query | both |
| Factual Correctness | answer aligns with structured gold annotation | both |
| Completeness | answer covers expected answer points | both |

### 8.4 Agent Metrics

These metrics apply to Agentic RAG. Traditional Hybrid RAG should report `N/A`.

| Metric | Definition |
|---|---|
| Intent Accuracy | predicted intent exactly matches `expected_intent` |
| Route Accuracy | route mode exactly matches retrieval/tool-only/tool-plus-retrieval gold |
| Tool Selection Accuracy | ordered selected tools match expected tool calls |
| Tool Input Accuracy | extracted fields match structured expected inputs |
| Tool Result Accuracy | tool outputs match expected outputs within declared tolerances |
| Tool Chain Completion Rate | expected tool chain completes successfully |
| Coverage Improvement Rate | round-level coverage improves when another retrieval round is triggered |
| Unsupported Claim Detection | verifier flags gold-labelled unsupported claims |
| Unsupported Claim Reduction | only reported when a real revision stage saves pre/post answers |

### 8.5 Robustness Metrics

| Metric | Definition |
|---|---|
| Chinese Accuracy | answer correctness on Chinese cases |
| Multi-turn Resolution Accuracy | final turn correctly uses conversation context |
| Negative Case Handling Accuracy | system avoids unsupported answers in negative cases |
| Noise Sensitivity | answer remains correct when retrieved context contains distractors |

Before any metric is reported, `app.evaluation.run_validation` must mark it
ready. Coverage improvement requires round-level coverage, noise sensitivity
requires clean/perturbed pairs, tool input accuracy requires structured expected
inputs, and multi-turn case metrics use aggregate rows rather than counting turn
rows as extra cases.

Overall comparison must be paired by case ID. Report the common-capability subset
separately from agentic-capability cases, include paired bootstrap confidence
intervals for continuous scores, and use a paired binary test such as McNemar for
pass/fail outcomes.

### 8.6 Efficiency Metrics

| Metric | Definition |
|---|---|
| Average Latency | average seconds per case |
| P95 Latency | 95th percentile latency |
| Failure Rate | timeout, exception, empty answer, or invalid output rate |
| Average Retrieval Rounds | mean retrieval rounds per case |
| Average Tool Calls | mean tool calls per case |

## 9. Evaluation Outputs

Artifacts should be written under:

```text
data/evaluation/
```

Required output files:

```text
data/evaluation/
  benchmark_candidates.jsonl
  benchmark_accepted_pool.jsonl
  benchmark_cases.jsonl
  benchmark_validation.jsonl
  sampling_manifest.json
  source_registry/
    sources.jsonl
    duplicate_map.jsonl
    snapshot_manifest.json
  source_graph/
    nodes.jsonl
    edges.jsonl
    graph_stats.json
  runs/
    traditional_hybrid_rag_results.jsonl
    agentic_rag_results.jsonl
  reports/
    summary.csv
    category_breakdown.csv
    language_breakdown.csv
    difficulty_breakdown.csv
    evaluation_report.md
```

Optional chart outputs:

```text
data/evaluation/reports/charts/
  answer_quality_comparison.png
  retrieval_metrics_comparison.png
  agent_metrics.png
  latency_comparison.png
  category_breakdown.png
```

## 10. Module Structure

Add the following modules:

```text
app/evaluation/
  __init__.py
  schemas.py
  dataset_loader.py
  source_registry.py
  source_graph.py
  benchmark_generator.py
  benchmark_validator.py
  benchmark_judge.py
  sampling.py
  run_validation.py
  statistics.py

  runners/
    __init__.py
    traditional_hybrid_rag.py
    agentic_rag.py

  metrics/
    __init__.py
    ragas_metrics.py
    retrieval_metrics.py
    citation_metrics.py
    answer_metrics.py
    agent_metrics.py
    robustness_metrics.py
    efficiency_metrics.py

  reporting/
    __init__.py
    summary_tables.py
    plots.py
    markdown_report.py
```

Add scripts:

```text
scripts/build_source_graph.py
scripts/build_evaluation_snapshot.py
scripts/generate_benchmark.py
scripts/judge_benchmark.py
scripts/validate_benchmark.py
scripts/sample_benchmark.py
scripts/run_evaluation.py
scripts/export_evaluation_report.py
```

## 11. Script Contracts

### 11.1 Build Evaluation Snapshot And Source Graph

```bash
python scripts/build_evaluation_snapshot.py \
  --chunks data/indexes/vector/chunks.json \
  --snapshot-date 2026-07-11
```

This eligibility gate must complete before source-graph construction. Expected
outputs are `sources.jsonl`, `duplicate_map.jsonl`, and
`snapshot_manifest.json` under `data/evaluation/source_registry/`.

```bash
python scripts/build_source_graph.py
```

Expected outputs:

```text
data/evaluation/source_graph/nodes.jsonl
data/evaluation/source_graph/edges.jsonl
data/evaluation/source_graph/graph_stats.json
```

Required options:

```bash
python scripts/build_source_graph.py --semantic-top-k 10 --semantic-threshold 0.72
```

### 11.2 Generate Benchmark Candidates

```bash
python scripts/generate_benchmark.py --target-candidates 700
```

Expected output:

```text
data/evaluation/benchmark_candidates.jsonl
```

### 11.3 Judge And Validate Benchmark

```bash
python scripts/judge_benchmark.py \
  --candidates data/evaluation/benchmark_candidates.jsonl \
  --source-registry data/evaluation/source_registry/sources.jsonl \
  --model independent-judge-model \
  --output data/evaluation/benchmark_judgements.jsonl

python scripts/validate_benchmark.py \
  --candidates data/evaluation/benchmark_candidates.jsonl \
  --source-registry data/evaluation/source_registry/sources.jsonl \
  --judge-assessments data/evaluation/benchmark_judgements.jsonl \
  --human-reviews data/evaluation/human_reviews.jsonl \
  --validation-output data/evaluation/benchmark_validation.jsonl \
  --accepted-output data/evaluation/benchmark_accepted_pool.jsonl \
  --require-accepted 300
```

Expected outputs:

```text
data/evaluation/benchmark_validation.jsonl
data/evaluation/benchmark_accepted_pool.jsonl
```

Select the final benchmark only after validation:

```bash
python scripts/sample_benchmark.py \
  --accepted-pool data/evaluation/benchmark_accepted_pool.jsonl \
  --validation-records data/evaluation/benchmark_validation.jsonl \
  --quota app/evaluation/default_benchmark_quota.json \
  --seed 42 \
  --output data/evaluation/benchmark_cases.jsonl \
  --manifest-output data/evaluation/sampling_manifest.json
```

### 11.4 Run Evaluation

```bash
python scripts/run_evaluation.py \
  --benchmark data/evaluation/releases/v1.0/benchmark.jsonl \
  --source-snapshot data/evaluation/releases/v1.0/source_snapshot_manifest.json \
  --systems B3 A1 A2 A3
```

Expected outputs:

```text
data/evaluation/runs/traditional_hybrid_rag_results.jsonl
data/evaluation/runs/agentic_rag_results.jsonl
```

### 11.5 Export Report

```bash
python scripts/export_evaluation_report.py \
  --benchmark data/evaluation/releases/v1.0/benchmark.jsonl \
  --results data/evaluation/runs/<run-id>/B3_results.jsonl data/evaluation/runs/<run-id>/A1_results.jsonl data/evaluation/runs/<run-id>/A2_results.jsonl data/evaluation/runs/<run-id>/A3_results.jsonl
```

Expected outputs:

```text
data/evaluation/reports/summary.csv
data/evaluation/reports/category_breakdown.csv
data/evaluation/reports/language_breakdown.csv
data/evaluation/reports/difficulty_breakdown.csv
data/evaluation/reports/evaluation_report.md
```

## 12. Runner Output Schema

Each system result row should use this schema:

```json
{
  "run_id": "run_001",
  "case_id": "case_001",
  "system": "agentic_rag",
  "row_type": "single_turn",
  "query": "...",
  "answer": "...",
  "retrieved_chunks": [
    {
      "chunk_id": "...",
      "rule_number": "14.34",
      "source_path": "...",
      "score": 0.091,
      "bm25_score": 0.7,
      "dense_score": 0.8
    }
  ],
  "citations": [
    {
      "chunk_id": "...",
      "rule_number": "14.34",
      "source_path": "..."
    }
  ],
  "route_decision": {},
  "tool_calls": [],
  "tool_results": [],
  "verification_result": {},
  "retrieval_rounds": [
    {
      "round_number": 1,
      "queries": ["..."],
      "chunk_ids": ["..."],
      "coverage_before": 0.0,
      "coverage_after": 0.8
    }
  ],
  "coverage_before": 0.0,
  "coverage_after": 0.8,
  "answer_before_verification": null,
  "answer_after_verification": null,
  "perturbation_id": null,
  "parent_case_id": null,
  "latency_seconds": 1.23,
  "error": null
}
```

For multi-turn cases, store one result per turn plus an aggregate final-turn result:

```json
{
  "case_id": "multi_001",
  "system": "agentic_rag",
  "turn_index": 2,
  "row_type": "turn",
  "conversation_id": "...",
  "answer": "..."
}
```

The final case-level row uses `row_type="aggregate"` and has no `turn_index`.
Only `single_turn` and `aggregate` rows enter case-level denominators. Every run
also writes a `RunManifest` containing benchmark, source snapshot, index, model,
prompt, generation-parameter, and code-revision hashes.

## 13. Report Structure

The generated evaluation report should contain:

1. Evaluation setup
2. Benchmark generation and validation method
3. Compared systems
4. Overall metric table
5. Breakdown by category
6. Breakdown by language
7. Breakdown by difficulty
8. Agent-specific metric table
9. Latency and failure analysis
10. Case studies
11. Limitations

Minimum tables:

| Table | Content |
|---|---|
| Table A | Benchmark distribution |
| Table B | Overall Traditional Hybrid RAG vs Agentic RAG comparison |
| Table C | RAGAS-compatible metrics |
| Table D | Agent-specific metrics |
| Table E | Category/language/difficulty breakdown |
| Table F | Negative and multi-turn performance |

## 14. Acceptance Criteria

The evaluation module is complete when all criteria below are met.

### 14.1 Source Graph

- source registry and snapshot manifest are generated before graph construction.
- archived, withdrawn, superseded, unknown, duplicate, and ineffective sources are excluded from main-benchmark gold eligibility.
- Main Board/GEM identity is preserved in every rule reference.
- `nodes.jsonl`, `edges.jsonl`, and `graph_stats.json` are generated.
- graph stats report node count, edge count, edge type counts, and scenario counts.
- rule reference edges and scenario edges are present.
- semantic edges are present when vector index files are available.

### 14.2 Benchmark

- at least 500 candidates are generated.
- exactly 300 accepted main benchmark cases are exported.
- language distribution is 210 English and 90 Chinese.
- difficulty distribution is 105 Easy, 135 Medium, 60 Hard.
- category distribution follows the 300-case table.
- all accepted cases pass schema validation.
- all accepted cases pass deterministic and type-specific validation.
- all accepted cases pass independent, case-type-aware structured judge validation.
- all accepted cases have recorded human source/rule approval.
- final selection has a fixed-seed sampling manifest and exact joint-cell quotas.

### 14.3 Evaluation Runs

- Traditional Hybrid RAG produces result JSONL for all 300 cases.
- Agentic RAG produces result JSONL for all 300 cases.
- multi-turn cases preserve turn order and conversation context.
- failures are recorded as rows, not silently dropped.
- every system has exactly one case-level row per case.
- run manifests freeze benchmark, snapshot, index, prompt, model, parameter, and code hashes.

### 14.4 Metrics

- retrieval metrics are computed for both systems.
- citation metrics are computed for both systems.
- answer metrics are computed for both systems.
- agent metrics are computed for Agentic RAG and marked `N/A` for Traditional Hybrid RAG.
- robustness and efficiency metrics are computed only after their readiness checks pass.
- system comparisons are paired by case ID and include confidence intervals.
- common-capability and agentic-capability subsets are reported separately.

### 14.5 Reporting

- `summary.csv` is generated.
- breakdown CSV files are generated.
- `evaluation_report.md` is generated.
- report includes tables suitable for direct use in the final thesis.

## 15. Implementation Order

Implement in this order:

1. strict schemas and dataset loader
2. source registry, canonical deduplication, and snapshot manifest
3. deterministic/type-specific validator, judge contract, and human gate
4. joint-quota sampler and sampling manifest
5. run contracts, metric-readiness checks, and paired statistics
6. source graph builder using only eligible canonical nodes
7. benchmark generator
8. Traditional Hybrid RAG runner
9. Agentic RAG runner
10. retrieval/citation/answer/agent/robustness/efficiency metrics
11. report exporter
12. integration tests and smoke tests

## 16. Important Constraints

- Do not evaluate frontend UI.
- Do not compare different answer-generation LLMs between evaluated systems. The benchmark judge should use an independent model; it is not an evaluated system.
- Use DeepSeek V4 Flash for evaluated system answers.
- Use the same HKEX knowledge base and index files for both systems.
- Keep Traditional Hybrid RAG non-agentic.
- Keep generated benchmark cases source-grounded at the answer-point level.
- Record generator model, judge model, prompt hashes, timestamp, source snapshot, source chunk IDs, human reviews, sampling seed, and run hashes.
- Do not include unsupported AI-generated legal claims in gold annotations.
- Do not report a metric when its readiness contract fails.
