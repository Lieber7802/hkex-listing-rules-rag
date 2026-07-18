# R2 Evaluation Preregistration

## Scope

R1 `v1.0` and its reported results remain frozen. Any R2 implementation work
uses development-only data. The formal R2 benchmark will be generated only
after the implementation commit, runtime configuration, and this document are
frozen.

## Formal Systems for the Next Confirmatory Release

| ID | System | Evidence selection | Tool evidence | Answer contract |
| --- | --- | --- | --- | --- |
| `B3` | Traditional hybrid RAG | Not applicable | Not applicable | Shared baseline generation |
| `A1` | Complete production Agentic RAG | `coverage_aware` | `regulatory_grounded` | `coverage_grounded` |
| `A2` | A1 without coverage-driven second retrieval | `coverage_aware` | `regulatory_grounded` | `coverage_grounded` |
| `A3` | A1 without tool execution | `coverage_aware` | `regulatory_grounded` | `coverage_grounded` |

All four systems must use the same frozen index, embedding model, answer LLM,
timeout, concurrency setting, and `v1.1` benchmark. The generation manifest
records planner and answer temperature as `0.0`.

`A2` differs from A1 only by `enable_coverage_retry=False` and
`max_retrieval_rounds=1`. `A3` differs from A1 only by
`enable_tools=False`. Historical `A1-legacy` and `A1-new` results are not
formal systems in this protocol.

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
quota, and a passed R2 isolation report against R1 `v1.0`. At least 20% of
cases must receive independent human review, stratified to include complex,
tool, and Chinese cases. Development candidates and any query text used in an
earlier evaluation run are not eligible for this release.

The existing `v1.1-r2-automated` release is retained as an automated
engineering artifact only. It does not satisfy this confirmatory benchmark
requirement and must not be retroactively relabelled as such.

## Primary Metric And Comparisons

The primary metric is Grounded Answer Completeness (GAC): an answer point
passes only when the answer covers the point, is judged correct for the
point's expected wording, and has its mapped source/tool evidence in the
system's citations or selected evidence.

The primary confirmation comparison is `A1` versus `B3` on GAC. The
change-attribution comparisons are `A1` versus `A2` and `A1` versus `A3` on
GAC, tool correctness, coverage, and retrieval rounds. GAC is the pooled ratio
of passed scorable answer points to all scorable answer points; cases with no
answer points are scored by their registered negative-behaviour metric and do
not enter the GAC denominator. Paired bootstrap resamples case clusters and
recomputes the pooled ratio on each resample. Binary end-to-end success
additionally uses McNemar's exact test.

An answer point passes only if a semantic judge verifies that the answer covers
the point correctly, the required source excerpt or actual tool output directly
supports the claim, and the answer does not overstate an unsupported regulatory
consequence. Deterministic identifier or token-overlap checks are diagnostics,
not the confirmatory GAC judge.

## Decision Rules

1. Claim an Agentic-RAG answer-completeness improvement over B3 only if the
   lower bound of the `A1 - B3` GAC 95% confidence interval is above zero.
2. Use `A1 - A2` and `A1 - A3` only as mechanism-attribution comparisons; they
   do not replace the primary comparison.
3. Require `A1` failure rate at or below 5%, tool-task correctness at or above
   80%, P95 latency at or below 24 seconds, and direct claim-to-citation
   precision no more than 2 percentage points below B3.
4. If a gate fails, report the failure and do not retune against the formal
   benchmark. Any later fix needs a new unseen release.

## Reproducibility And Stopping Rule

Record the git revision, model/provider, index hash, release hash, all policy
values, timeout, retry count, concurrency, Ollama readiness state, stage-level
latencies, and answer-judge configuration. If deterministic execution is not
guaranteed by the answer model, execute all four systems three times and report
the mean and variation. Once the formal run begins,
only checkpoint recovery is allowed; no prompt, threshold, policy, or case may
change. `scripts/judge_evaluation_answers.py` checkpoints by default and its
`--resume` mode reuses an assessment only when the system, case, answer hash,
and judge backend all match. `scripts/evaluate_r2_gates.py` evaluates the
decision rules mechanically and treats missing metrics as not evaluable.
