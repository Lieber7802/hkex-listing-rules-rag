from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from app.evaluation.schemas import (
    BenchmarkCase,
    CaseType,
    EvaluationRunRow,
    MetricReadiness,
    RowType,
)


def case_level_rows(rows: Iterable[EvaluationRunRow]) -> List[EvaluationRunRow]:
    return [
        row for row in rows
        if row.row_type in {RowType.SINGLE_TURN, RowType.AGGREGATE}
    ]


def validate_run_completeness(
    rows: Iterable[EvaluationRunRow],
    expected_case_ids: Iterable[str],
    systems: Iterable[str],
) -> Dict[str, List[str]]:
    row_list = list(rows)
    expected = set(expected_case_ids)
    issues: Dict[str, List[str]] = defaultdict(list)

    by_system_case: Dict[Tuple[str, str], List[EvaluationRunRow]] = defaultdict(list)
    for row in case_level_rows(row_list):
        by_system_case[(row.system, row.case_id)].append(row)

    for system in systems:
        actual = {case_id for row_system, case_id in by_system_case if row_system == system}
        for case_id in sorted(expected - actual):
            issues[system].append(f"missing case-level result: {case_id}")
        for case_id in sorted(actual - expected):
            issues[system].append(f"unexpected case-level result: {case_id}")
        for case_id in sorted(expected & actual):
            count = len(by_system_case[(system, case_id)])
            if count != 1:
                issues[system].append(
                    f"case {case_id} has {count} case-level rows; expected exactly one"
                )
    return dict(issues)


def _coverage_readiness(rows: Sequence[EvaluationRunRow]) -> MetricReadiness:
    candidates = [row for row in rows if row.retrieval_rounds]
    reasons: List[str] = []
    if not candidates:
        reasons.append("no rows contain retrieval-round records")
    for row in candidates:
        if row.coverage_before is None or row.coverage_after is None:
            reasons.append(f"{row.system}/{row.case_id}: missing case-level coverage before/after")
        for round_record in row.retrieval_rounds:
            if round_record.coverage_before is None or round_record.coverage_after is None:
                reasons.append(
                    f"{row.system}/{row.case_id}/round-{round_record.round_number}: "
                    "missing round coverage before/after"
                )
    return MetricReadiness(
        metric_name="coverage_improvement",
        ready=not reasons,
        reasons=list(dict.fromkeys(reasons)),
    )


def _claim_detection_readiness(rows: Sequence[EvaluationRunRow]) -> MetricReadiness:
    missing = [
        f"{row.system}/{row.case_id}"
        for row in case_level_rows(rows)
        if not isinstance(row.verification_result, dict)
        or "unsupported_claims" not in row.verification_result
    ]
    reasons = [f"missing unsupported_claims in verification_result: {item}" for item in missing]
    if not case_level_rows(rows):
        reasons.append("no case-level rows are available")
    return MetricReadiness(
        metric_name="unsupported_claim_detection",
        ready=not reasons,
        reasons=reasons,
    )


def _claim_reduction_readiness(rows: Sequence[EvaluationRunRow]) -> MetricReadiness:
    candidates = [
        row for row in case_level_rows(rows)
        if row.answer_before_verification is not None or row.answer_after_verification is not None
    ]
    reasons: List[str] = []
    if not candidates:
        reasons.append("no rows contain pre/post verification answers")
    for row in candidates:
        if row.answer_before_verification is None or row.answer_after_verification is None:
            reasons.append(f"{row.system}/{row.case_id}: incomplete pre/post answer pair")
    return MetricReadiness(
        metric_name="unsupported_claim_reduction",
        ready=not reasons,
        reasons=reasons,
    )


def _noise_readiness(rows: Sequence[EvaluationRunRow]) -> MetricReadiness:
    case_rows = case_level_rows(rows)
    clean_keys = {(row.system, row.case_id) for row in case_rows if not row.perturbation_id}
    perturbed = [row for row in case_rows if row.perturbation_id]
    reasons: List[str] = []
    if not perturbed:
        reasons.append("no perturbed case-level rows are available")
    for row in perturbed:
        parent_key = (row.system, row.parent_case_id or "")
        if parent_key not in clean_keys:
            reasons.append(
                f"{row.system}/{row.case_id}: clean parent {row.parent_case_id!r} is missing"
            )
    return MetricReadiness(
        metric_name="noise_sensitivity",
        ready=not reasons,
        reasons=reasons,
    )


def _multi_turn_readiness(
    rows: Sequence[EvaluationRunRow],
    cases: Optional[Sequence[BenchmarkCase]],
) -> MetricReadiness:
    reasons: List[str] = []
    if cases is None:
        return MetricReadiness(
            metric_name="multi_turn_resolution",
            ready=False,
            reasons=["benchmark cases are required to identify multi-turn cases"],
        )
    multi_ids = {case.case_id: len(case.turns) for case in cases if case.case_type == CaseType.MULTI_TURN}
    if not multi_ids:
        reasons.append("benchmark contains no multi-turn cases")
    by_system_case: Dict[Tuple[str, str], List[EvaluationRunRow]] = defaultdict(list)
    for row in rows:
        by_system_case[(row.system, row.case_id)].append(row)
    systems = {row.system for row in rows}
    for system in systems:
        for case_id, expected_turns in multi_ids.items():
            case_rows = by_system_case.get((system, case_id), [])
            aggregate = [row for row in case_rows if row.row_type == RowType.AGGREGATE]
            turns = [row for row in case_rows if row.row_type == RowType.TURN]
            if len(aggregate) != 1:
                reasons.append(
                    f"{system}/{case_id}: expected one aggregate row, found {len(aggregate)}"
                )
            if len(turns) != expected_turns:
                reasons.append(
                    f"{system}/{case_id}: expected {expected_turns} turn rows, found {len(turns)}"
                )
            indices = sorted(row.turn_index for row in turns if row.turn_index is not None)
            if indices and indices != list(range(1, expected_turns + 1)):
                reasons.append(f"{system}/{case_id}: turn indices are incomplete or duplicated")
    return MetricReadiness(
        metric_name="multi_turn_resolution",
        ready=not reasons,
        reasons=reasons,
    )


def _tool_input_readiness(
    rows: Sequence[EvaluationRunRow],
    cases: Optional[Sequence[BenchmarkCase]],
) -> MetricReadiness:
    reasons: List[str] = []
    if cases is None:
        return MetricReadiness(
            metric_name="tool_input_accuracy",
            ready=False,
            reasons=["benchmark cases are required for expected tool inputs"],
        )
    tool_case_ids: Set[str] = {
        case.case_id
        for case in cases
        if case.expected_tool_calls or any(turn.expected_tool_calls for turn in case.turns)
    }
    if not tool_case_ids:
        reasons.append("benchmark contains no expected tool calls")
    for row in case_level_rows(rows):
        if row.case_id not in tool_case_ids:
            continue
        if not row.tool_calls:
            reasons.append(f"{row.system}/{row.case_id}: actual tool_calls are missing")
            continue
        for index, call in enumerate(row.tool_calls, start=1):
            if not isinstance(call, dict) or not isinstance(call.get("inputs"), dict):
                reasons.append(
                    f"{row.system}/{row.case_id}/tool-{index}: inputs are missing"
                )
    return MetricReadiness(
        metric_name="tool_input_accuracy",
        ready=not reasons,
        reasons=reasons,
    )


def validate_metric_readiness(
    rows: Iterable[EvaluationRunRow],
    cases: Optional[Iterable[BenchmarkCase]] = None,
) -> Dict[str, MetricReadiness]:
    row_list = list(rows)
    case_list = list(cases) if cases is not None else None
    results = [
        _coverage_readiness(row_list),
        _claim_detection_readiness(row_list),
        _claim_reduction_readiness(row_list),
        _noise_readiness(row_list),
        _multi_turn_readiness(row_list, case_list),
        _tool_input_readiness(row_list, case_list),
    ]
    return {result.metric_name: result for result in results}
