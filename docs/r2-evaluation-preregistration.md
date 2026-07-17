# R2 Evaluation Preregistration

## Scope

R1 `v1.0` and its reported results remain frozen. Any R2 implementation work
uses development-only data. The formal R2 benchmark will be generated only
after the implementation commit, runtime configuration, and this document are
frozen.

## Formal Systems

| ID | System | Evidence selection | Tool evidence | Answer contract |
| --- | --- | --- | --- | --- |
| `B3` | Traditional hybrid RAG | Not applicable | Not applicable | Shared baseline generation |
| `A1-legacy` | Current Agentic behavior | `legacy` | `legacy` | `legacy` |
| `A1-new` | R2 optimized Agentic behavior | `coverage_aware` | `regulatory_grounded` | `coverage_grounded` |

All three systems must use the same frozen index, embedding model, answer LLM,
timeout, concurrency setting, and `v1.1` benchmark. The generation manifest
records planner and answer temperature as `0.0`.

## Formal Benchmark

The formal release targets 130 cases, with 65 English and 65 Chinese cases.
The exact joint quota is `app/evaluation/r2_v1_1_quota.json`:

- 30 single-rule queries;
- 35 complex regulation queries (obligation, procedure, or comparison);
- 35 tool cases (10 single-tool and 25 tool-chain);
- 15 multi-turn cases;
- 15 negative or insufficient-evidence cases.

Before freezing, the release must contain approved benchmark cases, independent
judge records, human reviews, validation records, source snapshot/graph,
quota, and a passed R2 isolation report against R1 `v1.0`. Development
candidates are not eligible for this release.

## Primary Metric And Comparisons

The primary metric is Grounded Answer Completeness (GAC): an answer point
passes only when the answer covers the point, is judged correct for the
point's expected wording, and has its mapped source/tool evidence in the
system's citations or selected evidence.

The primary confirmation comparison is `A1-new` versus `B3` on GAC. The R2
change-attribution comparison is `A1-new` versus `A1-legacy` on GAC. Both use
paired bootstrap differences with 10,000 resamples and 95% confidence
intervals. Binary end-to-end success additionally uses McNemar's exact test.

## Decision Rules

1. Claim an Agentic-RAG answer-completeness improvement over B3 only if the
   lower bound of the `A1-new - B3` GAC 95% confidence interval is above zero.
2. Treat R2 implementation as effective only when `A1-new - A1-legacy` GAC is
   at least +5 percentage points and its lower confidence bound is no worse
   than -2 percentage points. The -2pp value defines a material regression.
3. Require `A1-new` failure rate at or below 5%, tool-task correctness at or
   above 80%, P95 latency at or below 24 seconds, and citation precision no
   more than 2 percentage points below `A1-legacy`.
4. If a gate fails, report the failure and do not retune against the formal
   benchmark. Any later fix needs a new unseen release.

## Reproducibility And Stopping Rule

Record the git revision, model/provider, index hash, release hash, all policy
values, timeout, retry count, and Ollama readiness state. If deterministic
execution is not guaranteed by the answer model, execute all three systems
three times and report the mean and variation. Once the formal run begins,
only checkpoint recovery is allowed; no prompt, threshold, policy, or case may
change. `scripts/judge_evaluation_answers.py` checkpoints by default and its
`--resume` mode reuses an assessment only when the system, case, answer hash,
and judge backend all match. `scripts/evaluate_r2_gates.py` evaluates the
decision rules mechanically and treats missing metrics as not evaluable.
