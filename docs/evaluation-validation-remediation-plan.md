# Evaluation Validation Remediation Plan

Project: HKEX Listing Rules Compliance Agentic RAG System

Date: 2026-07-11

Status: Approved implementation plan for the evaluation validation foundation.

## 1. Objective

Build a defensible validation layer for the offline thesis benchmark. The layer must prevent stale or duplicated source material from becoming gold evidence, make every accepted case mechanically auditable, require recorded human approval, and guarantee that planned metrics can be computed from saved run artifacts.

This work is isolated from the online Agentic RAG workflow. Archive documents remain available for historical and noise stress tests, but they are not eligible as gold evidence for the current-rules main benchmark.

## 2. Fixed Assumptions

1. The main benchmark evaluates HKEX requirements that are current as of a frozen corpus snapshot date.
2. A source under an archive path, or explicitly marked withdrawn or superseded, is ineligible as main-benchmark gold evidence.
3. Unknown source status is ineligible by default. Eligibility must be established rather than assumed.
4. LLM judges assist validation but cannot independently establish legal ground truth.
5. Every accepted main-benchmark case requires at least one recorded human approval.
6. All sampling is deterministic for a fixed accepted pool, quota configuration, and seed.
7. Evaluation metrics may be reported only when their required run fields are present.

## 3. Deliverables

### 3.1 Source Registry And Snapshot

Implement `app/evaluation/source_registry.py` with:

- deterministic source-status inference;
- ruleset inference without discarding Main Board/GEM identity;
- normalized-text SHA-256 fingerprints;
- exact duplicate canonicalization;
- effective-date and snapshot-date eligibility checks;
- main-benchmark and stress-only eligibility flags;
- a corpus snapshot manifest containing source hash, policy version, counts, exclusions, and duplicate statistics.

Outputs:

```text
data/evaluation/source_registry/
  sources.jsonl
  duplicate_map.jsonl
  snapshot_manifest.json
```

### 3.2 Structured Gold Contract

Implement `app/evaluation/schemas.py` with type-safe models for:

- answerable, tool, multi-turn, and negative cases;
- primary category plus cross-cutting capability tags;
- expected intent and route mode;
- ruleset-aware rule references;
- required answer points mapped to exact supporting chunks;
- expected tool calls with inputs, outputs, order, and numeric tolerance;
- negative-case reason, expected action, and missing inputs;
- generator, judge, source-snapshot, and human-review provenance;
- per-turn annotations for multi-turn cases;
- run rows with an explicit `row_type` and metric grain.

Pydantic model validators must reject internally inconsistent cases before semantic validation.

### 3.3 Layered Benchmark Validation

Implement `app/evaluation/benchmark_validator.py` with four layers:

1. Schema validation through Pydantic.
2. Deterministic validation of source eligibility, answer-point evidence mappings, rule references, expected tool execution, language, and duplicate risk.
3. A structured LLM-judge assessment using an explicit 1-5 rubric and per-answer-point support decisions.
4. A recorded human review gate.

Acceptance must be derived from check records and must never be supplied as an unchecked input.

```text
accepted =
  schema_pass
  AND source_eligibility_pass
  AND type_specific_validation_pass
  AND every_required_answer_point_is_grounded
  AND rule_reference_validation_pass
  AND duplicate_check_pass
  AND judge_pass
  AND human_review_approved
```

Negative cases use separate profiles:

| Negative reason | Source requirement | Required behavior |
|---|---|---|
| nonexistent rule | no supporting source required | refuse or state not found |
| out of scope | no HKEX source required | state scope limitation |
| insufficient tool input | tool schema establishes missing fields | request clarification |
| ambiguous query | no specific rule required | request clarification |
| false premise | corrective evidence required | correct the premise with citations |

### 3.4 Human Review Protocol

The validator exports pending cases rather than silently accepting them. A human review record contains reviewer ID, status, timestamp, explicit per-dimension decisions, the exact reviewed chunk IDs, and notes. Source-backed approval is invalid unless all case evidence chunks are recorded.

For the final 300-case benchmark:

- all 300 cases require one source/rule review;
- a stratified 20% sample should receive a second review when a second reviewer is available;
- disagreements are adjudicated and retained in provenance;
- agreement is reported for categorical fields and evidence mappings.

`app.evaluation.statistics.human_review_agreement` reports the realized
second-review rate, exact status agreement, Cohen's kappa when defined,
per-dimension agreement, and exact/Jaccard evidence-mapping agreement.

The code enforces review presence and approval. Performing the review remains an explicit human action.

### 3.5 Reproducible Sampling

Implement `app/evaluation/sampling.py` with:

- exact joint category x language x difficulty quotas, with declared marginals;
- fixed-seed deterministic selection;
- explicit failure when the accepted pool cannot satisfy quotas;
- a sampling manifest with pool hash, seed, selected IDs, quotas, and deficits.

Cases are sampled from the accepted pool. Judge score must not be used as a quality ranking once the pass threshold is met.

### 3.6 Run And Metric Contracts

Implement `app/evaluation/run_validation.py` with:

- run-manifest provenance: benchmark hash, source snapshot hash, index hash, model identifier, prompt hash, generation parameters, code revision, and timestamps;
- per-turn versus aggregate row types;
- retrieval-round and coverage-before/after records;
- expected and actual tool-call details;
- optional pre-verification and post-verification answers;
- perturbation IDs for noise-sensitivity pairs;
- metric-readiness checks that block unsupported metrics.

Metric rules:

- coverage improvement requires round-level coverage;
- verifier quality is reported as unsupported-claim detection unless a real revision stage creates pre/post answers;
- noise sensitivity requires paired clean and perturbed runs;
- multi-turn case-level metrics use aggregate rows, while turn-level diagnostics use turn rows;
- system comparisons use paired case IDs and report confidence intervals.

### 3.7 Validation Scripts

Add:

```text
scripts/build_evaluation_snapshot.py
scripts/judge_benchmark.py
scripts/validate_benchmark.py
scripts/sample_benchmark.py
```

Both scripts must fail with a non-zero exit code for invalid input or unmet acceptance/sampling requirements and must never silently drop rows.

## 4. Verification Matrix

| Requirement | Automated evidence |
|---|---|
| archive/withdrawn sources excluded | source-registry unit tests |
| unknown sources fail closed | source-registry unit tests |
| exact duplicates canonicalized | duplicate-map tests |
| board identity preserved | rule-reference tests |
| answer points map to eligible chunks | benchmark-validator tests |
| tool inputs and outputs are reproducible | tool-case validation tests |
| negative cases use correct profile | parameterized negative-case tests |
| judge rubric is complete | judge-assessment schema tests |
| human approval cannot be bypassed | acceptance-gate tests |
| quotas and seed are reproducible | sampling tests |
| impossible quotas fail clearly | sampling deficit tests |
| unsupported metrics are blocked | metric-readiness tests |
| multi-turn rows are not double counted | run-contract tests |
| CLI artifacts round-trip | script smoke tests |

## 5. Implementation Order

1. Schemas and JSONL helpers.
2. Source registry and snapshot builder.
3. Deterministic and type-specific benchmark validator.
4. Judge and human-review acceptance gates.
5. Stratified sampler and sampling manifest.
6. Run schema and metric-readiness validator.
7. CLI scripts.
8. Focused tests, then full repository tests.

## 6. Completion Criteria

The remediation is complete only when:

- every deliverable above exists and has focused tests;
- all focused evaluation tests pass without an LLM, embedding service, or built index;
- the full repository test suite passes with an isolated empty index path;
- the implementation plan points to these contracts and no longer permits LLM-only gold acceptance;
- `git diff --check` reports no whitespace errors.
