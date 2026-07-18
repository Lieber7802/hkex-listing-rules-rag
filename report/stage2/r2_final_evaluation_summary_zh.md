# R2 Final Evaluation Summary

## Status

This is the final frozen R2 evaluation run. No post-result tuning, benchmark replacement, configuration change, or repeat run was performed.

- Run ID: `r2-auto-r1`
- Code revision: `38fb1fd40cdc6d65d2cf7c1a1d1b6b96dbefd4a6`
- Release: `v1.1-r2-automated`
- Benchmark: 130 frozen cases; 160 execution records per system because multi-turn cases add turn records.
- Systems: B3, A1, A2, A3.
- Generator: DeepSeek `deepseek-v4-flash`, temperature 0.
- Retriever: hybrid BM25 plus qwen3-embedding:4b; frozen index hash `04240c7c6d635f6b67d790a7b00625b5aa8da0d0c707bd87306ade8adb563c00`.
- Answer-point scorer: deterministic frozen-evidence scorer; 520 assessments. No additional LLM judge calls were used after the formal run.
- Case review mode: `automated_only`. No human legal-expert review was performed.

## Systems Compared

| ID | Role | Difference from the complete system |
| --- | --- | --- |
| B3 | Traditional hybrid RAG baseline | No planner, tools, coverage retry, evidence-selection contract, or answer-verification contract. |
| A1 | Complete Agentic RAG | LLM-primary planner, tools, coverage retry (up to two rounds), coverage-aware evidence selection, regulatory-grounded tool evidence, and coverage-grounded answer contract. |
| A2 | Coverage-retry ablation | Same as A1 except coverage retry is disabled and retrieval is limited to one round. |
| A3 | Tool ablation | Same as A1 except tools are disabled. |

## Final Results

| Metric | B3 | A1 | A2 | A3 |
| --- | ---: | ---: | ---: | ---: |
| Cases completed | 130 | 130 | 130 | 130 |
| Failure rate | 0.00% | 0.00% | 0.00% | 0.00% |
| Grounded Answer Completeness (GAC) | 38.46% | 33.72% | 34.74% | 41.60% |
| Answer-point coverage | 42.95% | 51.92% | 55.77% | 48.46% |
| Citation precision | 9.23% | 12.50% | 12.50% | 12.90% |
| Context recall | 84.58% | 82.24% | 82.24% | 83.18% |
| Mean latency | 12.84 s | 16.79 s | 15.24 s | 15.65 s |
| P95 latency | 24.32 s | 30.00 s | 29.03 s | 27.65 s |
| A1 tool-result accuracy | - | 100.00% | 100.00% | - |
| A1 coverage improvement rate | - | 55.56% | - | 55.56% |
| A1 second-retrieval rate | - | 6.92% | 0.00% | 6.92% |

## Paired Comparisons

The primary outcome is deterministic GAC. Differences are reported as the first system minus the second system, with a paired 10,000-sample bootstrap 95% confidence interval.

| Comparison | Mean GAC difference | 95% CI | Interpretation |
| --- | ---: | --- | --- |
| A1 minus B3 | -4.74 pp | [-11.86 pp, 2.24 pp] | The interval crosses zero. This run does not establish an overall GAC improvement over the traditional baseline. |
| A2 minus A1 | 1.03 pp | [-5.13 pp, 7.24 pp] | The interval crosses zero. The standalone effect of coverage retry is inconclusive on this benchmark. |
| A3 minus A1 | 7.88 pp | [1.03 pp, 14.55 pp] | The tool-disabled ablation scored higher under this deterministic GAC measure. This is an observed result, not evidence that tools are generally harmful. |

## R2 Gate Outcome

The R2 acceptance gate report is **not passed**. Five gates passed and two failed.

Passed:

- All required systems were present.
- A1 failure rate was 0%, below the 5% limit.
- A1 tool-result accuracy was 100%, above the 80% limit.
- A1 citation precision exceeded B3 by 3.27 percentage points.
- Both ablation comparisons were present.

Failed:

- Primary GAC gate: the lower confidence bound for A1 minus B3 was not above zero.
- A1 P95 latency was 30.00 seconds, above the 24-second operational threshold.

## What May Be Claimed

The final paper can safely state that the implemented Agentic RAG system is functionally complete for the assessed workflow: it completed all 130 cases without execution failures, achieved perfect tool-result accuracy on the benchmark's tool cases, and improved citation precision and ungrounded answer-point coverage relative to B3.

The final paper must not claim that this run proves Agentic RAG has superior overall grounded-answer completeness over traditional RAG. The preregistered primary comparison was negative and statistically inconclusive. It also must not claim human expert validation, because the case pool was automatically reviewed only.

## Required Limitations

1. The benchmark release was frozen after automated checks and automated-agent review. It did not receive legal-expert review.
2. GAC was scored with the frozen deterministic answer-point and evidence-mapping procedure, not a new LLM judge or human panel.
3. This is one formal run at temperature 0. DeepSeek does not provide a reproducible seed guarantee, so no cross-run variance estimate is available.
4. The primary GAC gate and A1 latency gate failed. They should be reported as failed rather than silently omitted.
5. Diagnostics requiring verifier fields are not available for B3, and tool-input accuracy is not meaningful for B3/A3 because those systems intentionally do not run tools.

## Paper-Ready Result Paragraph

On the frozen 130-case R2 benchmark, all four configurations completed without execution failures. The complete Agentic RAG configuration (A1) achieved 100% tool-result accuracy and improved citation precision from 9.23% for the traditional hybrid-RAG baseline (B3) to 12.50%, while answer-point coverage increased from 42.95% to 51.92%. However, the prespecified primary metric, deterministic grounded answer completeness, was 33.72% for A1 versus 38.46% for B3; the paired bootstrap difference was -4.74 percentage points (95% CI: -11.86 to 2.24). Therefore, this study does not claim a statistically confirmed overall GAC advantage for A1. A1 also incurred higher P95 latency (30.00 s versus 24.32 s for B3). These results show functional gains in routing, tool execution, evidence handling, and citation precision, while indicating that end-to-end grounded answer quality and latency remain open optimization targets.
