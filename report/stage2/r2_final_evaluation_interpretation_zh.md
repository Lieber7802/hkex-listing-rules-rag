# R2 Final Evaluation Interpretation and Thesis Writing Notes

## 1. Finalization Decision

The R2 implementation and its single frozen formal evaluation are final. The evaluation must not be followed by another improvement round, selective rerun, threshold change, or benchmark edit. This protects the integrity of the result and matches the project's deadline and cost constraint.

The code test suite had already passed before the formal run: `538 passed`. Python compilation, the frontend production build, and `git diff --check` also passed. The formal run itself completed with exit code 0 and generated four manifests, four raw result files, deterministic answer assessments, exported metrics, and a gate report.

## 2. What Was Improved in the System

The implementation work addressed both the original orchestration defects and the R2 evaluation infrastructure.

### 2.1 Retrieval and evidence flow

1. Second retrieval now uses the coverage gap, a query rewriter, and already-retrieved chunk exclusion. It records retrieval rounds instead of repeating the initial retrieval unchanged.
2. The reasoning node now consumes `selected_evidence` rather than silently reverting to all retrieved chunks. This aligns the answer context, citations, and verifier with the evidence-selection policy.
3. Coverage checking receives the planner intent, preserving its intended scoring strategy. In particular, obligation summaries use the dense retrieval signal instead of an inappropriate fused-score fallback.
4. An injected `IndexStore` now initializes the hybrid retriever correctly, so in-memory and end-to-end evaluation paths really perform retrieval.

### 2.2 Planning, tools, and safety

1. The planner is LLM-primary at temperature 0, with deterministic heuristics only as failure fallback. This supports questions whose intent is implicit rather than keyword-obvious.
2. Tool-plus-retrieval queries carry both computational results and regulatory evidence into the answer; tool-only queries still avoid inventing citations that do not exist.
3. The evidence selector, answer contract, and verifier provide explicit mechanisms for grounding regulatory conclusions in selected source material.
4. The legacy LangGraph workflow's useful second-retrieval behaviour was reintroduced deliberately, but through the current workflow's state and contracts rather than by reviving the obsolete file unchanged.

### 2.3 Evaluation engineering

1. Four fixed formal configurations were added: B3, A1, A2, and A3. A2 and A3 each change only one registered factor from A1.
2. The release contains 130 frozen cases, a source snapshot, benchmark hashes, automated-review traces, and a release manifest.
3. Execution is checkpointed per case and emits run manifests, allowing recovery without changing the benchmark or silently dropping failures.
4. The exporter produces system metrics, paired bootstrap intervals, CSV breakdowns, and machine-readable gate results.

## 3. How to Read the Final Numbers

### 3.1 Functional reliability is strong

All 130 cases completed in every configuration, so the observed failure rate is zero. A1 and A2 achieved 100% tool-result accuracy on the defined tool tasks. This is a real system result: the tool chain ran and returned the expected benchmark outputs.

### 3.2 Citation quality and answer-point coverage improved

A1 had higher citation precision than B3 (12.50% versus 9.23%) and higher ungrounded answer-point coverage (51.92% versus 42.95%). The latter is a diagnostic textual-coverage figure, not the primary GAC outcome, because it does not require the answer point to be evidence-grounded at the same time.

This distinction matters. A system can mention more expected points yet not show that each point was supported by the frozen evidence mapping. The system therefore should not use answer-point coverage alone to claim better legal-answer quality.

### 3.3 The primary conclusion is negative/inconclusive

The primary GAC result was lower for A1 than B3 (33.72% versus 38.46%). The paired bootstrap interval for A1 minus B3 was [-11.86 pp, 2.24 pp], which crosses zero. The evidence is therefore insufficient to claim an overall GAC improvement.

The most plausible engineering reading is that A1's more selective evidence contract and tool-aware workflow make source-to-answer matching stricter. B3 often includes a broader retrieval/citation set, which can score better under a deterministic mapping even when it is less selective. This is an interpretation, not a causal proof. The result should be presented as a trade-off exposed by the benchmark, not as a hidden success or a system failure.

### 3.4 The ablations are diagnostic, not a license for a new story

A2 did not differ reliably from A1 on GAC. Thus this final sample does not isolate a statistically clear benefit from coverage retry.

A3 scored higher than A1 under deterministic GAC, with a positive interval. This does not establish that tools reduce quality in all settings. A3 removes the need to integrate computational output and regulatory evidence in tool cases, so the deterministic answer-point/evidence contract can behave differently. With no new runs or human review, the safe claim is simply that the tool ablation outperformed A1 on this metric in this frozen evaluation.

## 4. Recommended Thesis Structure

### System section

Describe the system as an agentic orchestration contribution, not as a blanket accuracy claim:

> The revised workflow introduces LLM-primary routing with deterministic fallback, conditional coverage-driven second retrieval, evidence selection before synthesis, tool-plus-regulation evidence handling, and answer verification. The architecture was designed to make intermediate decisions inspectable and to ensure that retrieved and selected evidence flows into final generation.

Then explain A1/A2/A3 in one small table. Do not describe them as six configurations; the final formal protocol has exactly four systems.

### Evaluation section

Use the R2 Final Evaluation Summary table. State that B3 is the traditional hybrid-RAG baseline, A1 is the full system, A2 removes coverage retry, and A3 removes tools. State that all configurations used the same frozen source snapshot, index, model, temperature, and 130-case benchmark.

### Results section

Lead with the exact primary result, then the functional strengths:

> The principal GAC comparison did not demonstrate a statistically confirmed advantage for the complete Agentic RAG configuration. Nevertheless, A1 completed all cases, achieved 100% tool-result accuracy, and improved citation precision and answer-point coverage. The result therefore supports the system's functional orchestration benefits while identifying evidence-grounded synthesis and tail latency as remaining limitations.

### Limitations section

State all of the following explicitly:

- Cases were automatically reviewed, not reviewed by human legal experts.
- The primary score used deterministic answer-point/evidence mapping.
- One frozen run was conducted; external model nondeterminism was not measured through repeated runs.
- The primary GAC and A1 P95 latency gates did not pass.
- Tool-input metrics are not meaningful for B3/A3 because their definitions intentionally omit tools.

## 5. What Not to Write

- Do not state that Agentic RAG outperformed traditional RAG overall.
- Do not state that the benchmark was expert-validated or human-reviewed.
- Do not replace GAC with answer-point coverage as the headline result.
- Do not report A3's GAC as proof that tools are harmful.
- Do not suppress the failed latency threshold or the single-run limitation.
- Do not imply six formal configurations; only B3, A1, A2, and A3 are formal.

## 6. Reproducibility Record

The raw artifacts needed for the paper are retained locally:

- Frozen release: `data/evaluation/releases/v1.1-r2-automated/`.
- Raw execution: `data/evaluation/runs/r2-auto-r1/`.
- Exported tables and gate report: `data/evaluation/reports/r2-auto-r1/`.
- Code revision: `38fb1fd40cdc6d65d2cf7c1a1d1b6b96dbefd4a6`.

The release manifest records the automated-only review restriction, source snapshot, benchmark hash, and all frozen input hashes. The run manifests record the model, temperatures, index hash, seed field, and per-system configuration.
