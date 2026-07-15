# Evaluation Experiment Protocol

## Purpose

This protocol separates system development from final measurement for the HKEX Listing Rules Agentic RAG project. It applies to every experiment reported as a final result in the dissertation.

The protocol does not claim that any system configuration has been evaluated. It defines the conditions under which future results may be compared.

## Frozen Test Release

The final test set is release `v1.0`:

- Release directory: `data/evaluation/releases/v1.0/`
- Benchmark: `benchmark.jsonl`
- Cases: 300
- Source snapshot: `snapshot-2026-07-11-2cc96f13fdd6`
- Benchmark SHA-256: `e891d6985dda544348aa545e0eccec90b941c4471d510f5138ac21ffd12450bd`
- Release manifest: `data/evaluation/releases/v1.0/release_manifest.json`

The release contains the benchmark, Terra High judgements, task-owner approvals, validation records, the source snapshot manifest, Source Graph statistics, and the joint quota. The release manifest records the hash of every copied artifact.

Do not modify any file inside `data/evaluation/releases/v1.0/`. A change to a benchmark item, gold answer point, approval, judgement, source snapshot, or quota requires a new release version such as `v1.1`; it must not replace `v1.0`.

## Data Access Rules

During implementation and system repair, developers may use unit tests, API integration tests, curated smoke queries, and the 32-case pilot data under `data/evaluation/pilot/`. They must not inspect, run, score, or use individual `v1.0` queries to select prompts, thresholds, routes, retrieval parameters, tool logic, or model settings.

The pilot set is a development aid only. Its post-reassessment validation contains no human-approved cases, so it must not be presented as a formal benchmark or combined with `v1.0` metrics.

The final test release may be opened only for:

1. verifying its release manifest before an evaluation run;
2. executing a pre-registered final evaluation script; or
3. investigating a confirmed execution defect after results have been recorded.

If a `v1.0` result changes a system decision, the affected result is exploratory. The corrected system must be evaluated against a new unseen test release or be reported as post-hoc analysis rather than the primary final result.

## Development Sequence

1. Repair system issues using unit tests, integration tests, smoke queries, and the pilot set.
2. Record each selected system configuration in a versioned experiment config before final evaluation.
3. Freeze the code revision, index files, source snapshot, prompt templates, model settings, seeds, and evaluation script.
4. Verify every release artifact hash against `release_manifest.json`.
5. Run each pre-registered configuration once on all 300 cases.
6. Aggregate results, confidence intervals, and error categories without changing the tested configuration.
7. Report primary results, limitations, and any post-hoc repairs separately.

## Planned Configurations

The final experiment should compare configurations with a common source snapshot, model family, decoding settings, retrieval cut-off, and tool implementation unless the configuration explicitly studies that factor.

| ID | Configuration | Primary question |
| --- | --- | --- |
| B3 | Hybrid BM25+dense RRF retrieval plus answer synthesis | Does hybrid retrieval improve the retrieval baseline? |
| A1 | Full Agentic RAG workflow | What is the end-to-end result of the proposed system? |
| A2 | A1 without the coverage-driven second retrieval loop | Does the coverage loop improve evidence retrieval? |
| A3 | A1 without computation-tool execution for tool cases | Do deterministic tools improve tool-task correctness? |

Only B3, A1, A2 and A3 are pre-registered for the final comparison. Configurations A2 and A3 must be implemented as explicit, documented switches. Do not emulate an ablation by manually editing answers or selectively dropping cases.

## Required Run Record

Each run must save a machine-readable record with:

- release version and verified manifest hash;
- code revision or commit hash;
- source snapshot and index hashes;
- configuration ID and full parameter values;
- LLM provider, model identifier, temperature, token limits, and prompt version hashes;
- embedding model and retrieval parameters, including BM25 and dense top-k, RRF k, and final top-k;
- seed, start and end time, completed-case count, failures, retry count, and latency measurements;
- raw per-case outputs, retrieved chunk IDs, route decision, tool calls, citations, and evaluator outcomes.

Use deterministic decoding where the provider supports it. If an unavoidable component remains stochastic, document the source of variation and run the same pre-registered configuration at least three times with different recorded seeds. Report the mean and spread rather than the best run.

## Metrics

Report an overall result and stratified results by category, language, difficulty, and case type. Small strata, especially the 20 negative and 25 multi-turn cases, are diagnostic results rather than evidence for broad statistical claims.

| Layer | Metrics |
| --- | --- |
| Retrieval | expected-chunk Recall@k, rule coverage, reciprocal rank of the first expected chunk |
| Planning | expected route accuracy, intent accuracy, tool-selection accuracy |
| Tools | exact tool-output match, required-input extraction accuracy, chain completion rate |
| Answer | required answer-point coverage, cited-rule correctness, evidence grounding, negative-case behavior correctness |
| System | end-to-end task success, p50/p95 latency, failure rate, fallback rate, second-retrieval rate |

For binary outcomes, report the numerator, denominator, percentage, and a 95% confidence interval. Use paired comparisons between configurations because every configuration answers the same fixed cases. For a primary end-to-end comparison, use paired bootstrap intervals or McNemar's test and state the chosen method before the run.

## Scoring Rules

Retrieval and structured workflow metrics should be computed directly from the benchmark's expected chunk IDs, rules, routes, answer points, and tool expectations. Generated answers require a documented evaluation rubric. Reuse the same answer-point and evidence-grounding criteria for every configuration.

Any model-based answer judge must be independent from the answer generator and must receive the same prompt, source evidence, and acceptance threshold for every configuration. Retain judge inputs and outputs. A human spot check of reported failures and disputed judge decisions should be described as qualitative verification, not as a replacement for the recorded metric.

## Reporting Rules

The dissertation must distinguish:

- approved benchmark construction and validation;
- development-set observations;
- pre-registered final test results; and
- post-hoc debugging or analysis.

State that task-owner approval was recorded as a batch approval after sampled human review of the review packet. Do not describe it as 300 independently performed manual legal reviews.

## Immediate Next Step

Resolve the outstanding system issues without using `v1.0` queries for tuning. Once the system is stable, implement the run recorder and metric calculators, pre-register the configurations above, and then run the frozen release once for final measurement.
