# R2 Acceptance Audit

## Decision

The current R2 artifacts are reproducible as an automated engineering run, but they do **not** satisfy the written plan's confirmatory acceptance conditions. The active objective "implement and evaluate until acceptance passes" is therefore not complete.

This audit is read-only with respect to the frozen benchmark and raw run. It does not overwrite `r2-auto-r1` or reinterpret a failed gate as passed.

## Verified Strengths

| Requirement | Evidence | Status |
| --- | --- | --- |
| Four formal configurations execute on the same frozen release | B3/A1/A2/A3 manifests share code revision, model, index, and release hash | Pass |
| Case-level completeness | 130 cases per system; exactly one terminal row per case | Pass |
| Runtime reliability | All four manifests report zero failures | Pass |
| Tool output correctness | A1 and A2 report 100% tool-result accuracy | Pass |
| Automated release traceability | Release manifest hashes benchmark, source snapshot, judge, automated review, validation, and quota artifacts | Pass, automated-only |
| Regression validation | `pytest -q` reports 538 passed; frontend production build passes | Pass |

## Acceptance Failures

### 1. Primary GAC is not valid under the written definition

The plan requires every GAC point to be covered, correct, directly evidence-supported, and not overstate an uncertain legal consequence. The current default scorer does not establish those properties:

- Deterministic scoring sets `correct = answered`; `answered` is a token-overlap heuristic. It cannot distinguish a wrong number, negation, rule number, or unsupported legal consequence.
- Grounding is determined by mapped chunk/tool identifier overlap, not claim-to-excerpt entailment.
- Unsupported claims are copied into the assessment but do not affect the point's pass state.
- Negative cases without answer points receive a GAC of 1.0 automatically.
- The exported metric is a macro average of per-case values, whereas the plan defines point-level passed points divided by expected answer points.

The benchmark has 212 scorable answer points: 82 cases have one point, 25 have four, 10 have three, and 13 negative cases have zero. The table makes the metric mismatch explicit.

| System | Exported case-macro deterministic value | Point-pooled deterministic diagnostic |
| --- | ---: | ---: |
| B3 | 38.46% | 47 / 212 = 22.17% |
| A1 | 33.72% | 43 / 212 = 20.28% |
| A2 | 34.74% | 46 / 212 = 21.70% |
| A3 | 41.60% | 58 / 212 = 27.36% |

With the same 10,000 resamples and seed, a case-cluster weighted bootstrap for the point-pooled deterministic diagnostic gives A1 minus B3 `-1.89pp` (95% CI `[-8.21pp, 4.09pp]`), rather than the exported macro-average `-4.74pp` (95% CI `[-11.86pp, 2.24pp]`). Neither supports the desired positive claim. The distinction matters because the exported number is not the plan's defined metric.

The initial deterministic comparison is consequently an exploratory diagnostic, not a valid confirmation or refutation of the plan's primary hypothesis.

## 2. Explicit operational gate failure

A1 P95 end-to-end latency is `30.0015s`, above the plan's `24s` maximum. This is real processing time measured around `orchestrator.process_query`, not a report/export artifact or a 30-second timeout. Tool-chain and comparison cases dominate the tail.

## 3. Release and protocol non-compliance

| Written requirement | Current evidence | Status |
| --- | --- | --- |
| Independent/human review for complex or disputed cases | Release is explicitly `automated_only`; `human_review_status=not_performed` | Not met |
| Three full repeats when answer-model determinism is not guaranteed | DeepSeek has no verified seed guarantee; only one formal run exists | Not met |
| Unseen v1.1 formal set | Final release has query overlap with earlier v1.1 candidate/runs | Not proven |
| Unified formal-system documentation | Preregistration says B3/A1-legacy/A1-new; final run says B3/A1/A2/A3 | Not met |
| Unsupported-claim rate support metric | Export marks it not ready | Not met |

## System Findings That Must Be Fixed Before a New Confirmatory Release

1. Multi-gap second retrieval merges all results then slices to ten, allowing the first gap to crowd out evidence for later gaps.
2. `obligation_summary` can be labelled `tool_plus_retrieval` but not actually execute its checklist tool.
3. A successful tool call can cause answer verification to mark a contradictory answer as supported without comparing the answer against the tool output.
4. Reasoning cites the full selected set rather than the specific evidence used for each claim; Chinese rule references also miss exact-rule prioritisation.
5. All A1 requests fell back from the LLM planner in the formal run, while retaining the planner's latency cost. The fallback reason is not recorded.

## Only Valid Route to Confirmatory Acceptance

1. Repair the scoring and orchestration defects under tests, including semantic correctness, claim-to-evidence support, tool-output contradiction checks, negative-case scoring, point-level GAC aggregation, multi-turn scoring, and stage-level latency observations.
2. Update the preregistration and release protocol before generating data so B3/A1/A2/A3, review rules, metric definitions, and stopping rules are consistent.
3. Create a new unseen release with a distinct benchmark version; do not alter or reuse the frozen `v1.1-r2-automated` as confirmation data.
4. Complete the registered independent review (at least the required complex/tool/Chinese sampling), then freeze the release.
5. Run B3/A1/A2/A3 under the frozen conditions. If the answer model remains non-deterministic, perform three complete repetitions and report mean and variation.
6. Run the mechanical gates. If they fail, report them and stop rather than tuning against that release.

## Immediate Reporting Constraint

Until the above route is completed, the paper may describe `r2-auto-r1` as an automated engineering evaluation that demonstrates execution reliability and tool-result accuracy. It must not call the run a human-validated confirmatory evaluation or claim an overall grounded-answer-completeness result.
