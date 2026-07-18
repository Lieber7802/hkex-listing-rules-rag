from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from app.evaluation.run_validation import case_level_rows, validate_metric_readiness
from app.evaluation.schemas import (
    BenchmarkCase,
    EvaluationRunRow,
    GroundedAnswerAssessment,
    MetricReadiness,
)
from app.evaluation.statistics import (
    mcnemar_exact,
    paired_bootstrap_difference,
    paired_clustered_pooled_bootstrap_difference,
)


def _expected_for_case(case: BenchmarkCase):
    if case.turns:
        final = case.turns[-1]
        return final.expected_intent.value, final.expected_route.value, final.answer_points, final.expected_tool_calls
    return case.expected_intent.value, case.expected_route.value, case.answer_points, case.expected_tool_calls


def _contains_point(answer: str, point: str) -> bool:
    tokens = [token.lower() for token in point.split() if len(token) > 3]
    return bool(tokens) and sum(token in answer.lower() for token in tokens) / len(tokens) >= 0.5


def evaluate_rows(
    rows: Iterable[EvaluationRunRow],
    cases: Iterable[BenchmarkCase],
    grounded_assessments: Iterable[GroundedAnswerAssessment] | None = None,
) -> dict:
    rows = list(rows)
    grounded_assessments = list(grounded_assessments or [])
    case_map = {case.case_id: case for case in cases}
    grouped = defaultdict(list)
    case_rows = case_level_rows(rows)
    assessment_map = {
        (assessment.system, assessment.case_id): assessment
        for assessment in grounded_assessments
    }
    grounded_readiness = _grounded_answer_readiness(case_rows, case_map, assessment_map)
    for row in case_rows:
        grouped[row.system].append(row)
    output = {
        "systems": {},
        "readiness": {"grounded_answer_completeness": grounded_readiness.model_dump()},
    }
    for system, system_rows in grouped.items():
        hits5 = hits10 = citations = answer_scores = route_scores = intent_scores = tool_scores = 0
        recall_scores = []
        reciprocal_ranks = []
        tool_input_scores = []
        tool_result_scores = []
        chain_scores = []
        coverage_improvements = []
        second_retrievals = 0
        context_precisions = []
        rule_coverages = []
        citation_precisions = []
        negative_scores = []
        multi_turn_scores = []
        latencies = []
        grounded_passed_points = 0
        grounded_scorable_points = 0
        for row in system_rows:
            case = case_map[row.case_id]
            intent, route, points, expected_tools = _expected_for_case(case)
            actual_ids = [item.get("chunk_id") for item in row.retrieved_chunks]
            gold_ids = set(case.source_chunk_ids)
            hits5 += bool(gold_ids & set(actual_ids[:5]))
            hits10 += bool(gold_ids & set(actual_ids[:10]))
            if gold_ids:
                recall_scores.append(len(gold_ids & set(actual_ids)) / len(gold_ids))
                context_precisions.append(len(gold_ids & set(actual_ids)) / len(actual_ids) if actual_ids else 0.0)
                first_rank = next((index + 1 for index, chunk_id in enumerate(actual_ids) if chunk_id in gold_ids), None)
                reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)
            citation_ids = {item.get("chunk_id") for item in row.citations}
            citations += bool(gold_ids & citation_ids)
            if citation_ids:
                citation_precisions.append(len(gold_ids & citation_ids) / len(citation_ids))
            expected_rules = {rule.rule_number.lower() for rule in case.expected_rules}
            retrieved_rules = {str(item.get("rule_number", "")).lower() for item in row.retrieved_chunks}
            if expected_rules:
                rule_coverages.append(len(expected_rules & retrieved_rules) / len(expected_rules))
            answer_scores += (sum(_contains_point(row.answer, point.text) for point in points) / len(points)) if points else 1.0
            assessment = assessment_map.get((system, row.case_id))
            if assessment is not None:
                outcomes = _assessment_point_outcomes(assessment, points)
                if outcomes is not None:
                    grounded_passed_points += sum(outcomes)
                    grounded_scorable_points += len(outcomes)
            if case.case_type.value == "negative":
                expectation = case.negative_expectation
                required = expectation.expected_message_points if expectation else []
                negative_scores.append(
                    sum(_contains_point(row.answer, item) for item in required) / len(required)
                    if required else int(bool(row.answer.strip()))
                )
            if case.turns:
                multi_turn_scores.append(
                    sum(_contains_point(row.answer, point.text) for point in points) / len(points)
                    if points else int(bool(row.answer.strip()))
                )
            decision = row.route_decision or {}
            mode = decision.get("tool_decision", {}).get("tool_mode") or "retrieval"
            if mode == "none":
                mode = "retrieval"
            intent_scores += bool(decision.get("intent") == intent)
            route_scores += bool(mode == route)
            if expected_tools:
                tool_scores += [call.get("tool_name") for call in row.tool_calls] == [tool.tool_name for tool in expected_tools]
                actual_calls = row.tool_calls
                per_call_inputs = []
                per_call_results = []
                for expected in expected_tools:
                    actual = next((call for call in actual_calls if call.get("tool_name") == expected.tool_name), None)
                    per_call_inputs.append(bool(actual) and all(actual.get("inputs", {}).get(key) == value for key, value in expected.inputs.items()))
                    actual_result = next((result for result in row.tool_results if result.get("tool_name") == expected.tool_name), None)
                    expected_output = expected.expected_output
                    if not expected_output:
                        per_call_results.append(bool(actual_result and actual_result.get("success")))
                    else:
                        actual_output = (actual_result or {}).get("output") or {}
                        per_call_results.append(bool(actual_result and actual_result.get("success")) and all(
                            abs(float(actual_output[key]) - float(value)) <= expected.numeric_tolerances.get(key, 0.0)
                            if isinstance(value, (int, float)) and key in actual_output else actual_output.get(key) == value
                            for key, value in expected_output.items()
                        ))
                tool_input_scores.append(sum(per_call_inputs) / len(per_call_inputs))
                tool_result_scores.append(sum(per_call_results) / len(per_call_results))
                chain_scores.append(len(row.tool_results) >= len(expected_tools) and all(result.get("success") for result in row.tool_results[:len(expected_tools)]))
            if row.retrieval_rounds:
                second_retrievals += int(len(row.retrieval_rounds) > 1)
                coverage_improvements.extend(
                    int(round_.coverage_after > round_.coverage_before)
                    for round_ in row.retrieval_rounds
                    if round_.coverage_before is not None and round_.coverage_after is not None and round_.round_number > 1
                )
            latencies.append(row.latency_seconds)
        count = len(system_rows)
        output["systems"][system] = {
            "case_count": count, "hit_at_5": hits5 / count if count else None,
            "hit_at_10": hits10 / count if count else None,
            "context_recall": sum(recall_scores) / len(recall_scores) if recall_scores else None,
            "context_precision": sum(context_precisions) / len(context_precisions) if context_precisions else None,
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else None,
            "rule_coverage": sum(rule_coverages) / len(rule_coverages) if rule_coverages else None,
            "citation_hit_rate": citations / count if count else None,
            "citation_precision": sum(citation_precisions) / len(citation_precisions) if citation_precisions else None,
            "answer_point_coverage": answer_scores / count if count else None,
            "grounded_answer_completeness": (
                grounded_passed_points / grounded_scorable_points
                if grounded_scorable_points
                else None
            ),
            "grounded_answer_passed_points": grounded_passed_points,
            "grounded_answer_scorable_points": grounded_scorable_points,
            "faithfulness": None, "response_relevancy": None, "factual_correctness": None,
            "intent_accuracy": intent_scores / count if system != "B3" and count else None,
            "route_accuracy": route_scores / count if system != "B3" and count else None,
            "tool_selection_accuracy": tool_scores / sum(bool(_expected_for_case(case_map[row.case_id])[3]) for row in system_rows) if any(_expected_for_case(case_map[row.case_id])[3] for row in system_rows) else None,
            "tool_input_accuracy": sum(tool_input_scores) / len(tool_input_scores) if tool_input_scores else None,
            "tool_result_accuracy": sum(tool_result_scores) / len(tool_result_scores) if tool_result_scores else None,
            "tool_chain_completion_rate": sum(chain_scores) / len(chain_scores) if chain_scores else None,
            "coverage_improvement_rate": sum(coverage_improvements) / len(coverage_improvements) if coverage_improvements else None,
            "second_retrieval_rate": second_retrievals / count if count else None,
            "negative_case_handling_accuracy": sum(negative_scores) / len(negative_scores) if negative_scores else None,
            "multi_turn_resolution_accuracy": sum(multi_turn_scores) / len(multi_turn_scores) if multi_turn_scores else None,
            "failure_rate": sum(bool(row.error or not row.answer.strip()) for row in system_rows) / count if count else None,
            "average_latency_seconds": sum(latencies) / count if count else None,
            "p50_latency_seconds": _quantile(latencies, 0.5) if latencies else None,
            "p95_latency_seconds": _quantile(latencies, 0.95) if latencies else None,
        }
    readiness = validate_metric_readiness(rows, cases)
    output["readiness"].update({key: value.model_dump() for key, value in readiness.items()})
    gate_map = {
        "coverage_improvement_rate": "coverage_improvement",
        "tool_input_accuracy": "tool_input_accuracy",
        "multi_turn_resolution_accuracy": "multi_turn_resolution",
    }
    output["not_reported_metrics"] = []
    for metrics in output["systems"].values():
        for metric, readiness_key in gate_map.items():
            if not readiness[readiness_key].ready:
                metrics[metric] = None
                output["not_reported_metrics"].append(metric)
        if not grounded_readiness.ready:
            metrics["grounded_answer_completeness"] = None
            output["not_reported_metrics"].append("grounded_answer_completeness")
    output["not_reported_metrics"] = sorted(set(output["not_reported_metrics"] + [
        "faithfulness", "response_relevancy", "factual_correctness",
        "noise_sensitivity", "unsupported_claim_detection", "unsupported_claim_reduction",
    ]))
    output["paired_comparisons"] = _paired_comparisons(
        grouped,
        case_map,
        assessment_map,
        grounded_readiness.ready,
    )
    return output


def _grounded_answer_readiness(
    rows: Sequence[EvaluationRunRow],
    case_map: Mapping[str, BenchmarkCase],
    assessment_map: Mapping[tuple[str, str], GroundedAnswerAssessment],
) -> MetricReadiness:
    reasons = []
    scorable_point_count = 0
    for row in rows:
        assessment = assessment_map.get((row.system, row.case_id))
        if assessment is None:
            reasons.append(f"missing grounded assessment: {row.system}/{row.case_id}")
            continue
        answer_hash = hashlib.sha256(row.answer.encode("utf-8")).hexdigest()
        if assessment.answer_hash != answer_hash:
            reasons.append(f"stale grounded assessment for changed answer: {row.system}/{row.case_id}")
        if not assessment.judge_backend.startswith("llm:"):
            reasons.append(
                f"non-semantic diagnostic assessment cannot support formal GAC: "
                f"{row.system}/{row.case_id} ({assessment.judge_backend})"
            )
        case = case_map[row.case_id]
        _, _, points, _ = _expected_for_case(case)
        scorable_point_count += len(points)
        outcomes = _assessment_point_outcomes(assessment, points)
        if outcomes is None:
            reasons.append(
                f"grounded assessment point IDs do not match the benchmark: "
                f"{row.system}/{row.case_id}"
            )
    if not rows:
        reasons.append("no case-level rows are available")
    if scorable_point_count == 0:
        reasons.append("no scorable answer points are available")
    return MetricReadiness(
        metric_name="grounded_answer_completeness",
        ready=not reasons,
        reasons=reasons,
    )


def _quantile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower, upper = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _assessment_point_outcomes(
    assessment: GroundedAnswerAssessment,
    points,
) -> list[bool] | None:
    expected_ids = [point.point_id for point in points]
    assessments_by_id = {point.point_id: point for point in assessment.point_assessments}
    if (
        len(assessment.point_assessments) != len(assessments_by_id)
        or set(assessments_by_id) != set(expected_ids)
    ):
        return None
    return [assessments_by_id[point_id].passed for point_id in expected_ids]


def _paired_comparisons(grouped, case_map, assessment_map, grounded_ready):
    comparisons = {}
    for baseline, candidate in (
        ("B3", "A1"), ("A1", "A2"), ("A1", "A3"),
        ("B3", "A1-new"), ("A1-legacy", "A1-new"),
    ):
        baseline_rows = {row.case_id: row for row in grouped.get(baseline, [])}
        candidate_rows = {row.case_id: row for row in grouped.get(candidate, [])}
        if not baseline_rows or set(baseline_rows) != set(candidate_rows):
            continue
        baseline_success = {case_id: not row.error and bool(row.answer.strip()) for case_id, row in baseline_rows.items()}
        candidate_success = {case_id: not row.error and bool(row.answer.strip()) for case_id, row in candidate_rows.items()}
        baseline_scores = {case_id: float(value) for case_id, value in baseline_success.items()}
        candidate_scores = {case_id: float(value) for case_id, value in candidate_success.items()}
        comparisons[f"{candidate}_vs_{baseline}"] = {
            "paired_bootstrap": paired_bootstrap_difference(baseline_scores, candidate_scores).model_dump(),
            "mcnemar": mcnemar_exact(baseline_success, candidate_success).model_dump(),
        }
        baseline_grounded = {
            case_id: _assessment_point_outcomes(
                assessment_map[(baseline, case_id)],
                _expected_for_case(case_map[case_id])[2],
            )
            for case_id in baseline_rows
            if (baseline, case_id) in assessment_map
        }
        candidate_grounded = {
            case_id: _assessment_point_outcomes(
                assessment_map[(candidate, case_id)],
                _expected_for_case(case_map[case_id])[2],
            )
            for case_id in candidate_rows
            if (candidate, case_id) in assessment_map
        }
        if (
            grounded_ready
            and set(baseline_grounded) == set(baseline_rows)
            and set(candidate_grounded) == set(candidate_rows)
            and all(outcomes is not None for outcomes in baseline_grounded.values())
            and all(outcomes is not None for outcomes in candidate_grounded.values())
        ):
            comparisons[f"{candidate}_vs_{baseline}"]["grounded_answer_completeness"] = (
                paired_clustered_pooled_bootstrap_difference(
                    baseline_grounded,
                    candidate_grounded,
                ).model_dump()
            )
    return comparisons
