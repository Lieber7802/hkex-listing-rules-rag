"""Mechanical acceptance gates for the preregistered R2 evaluation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.evaluation.schemas import StrictModel


MATERIAL_REGRESSION_TOLERANCE = 0.02


class R2GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class R2GateResult(StrictModel):
    name: str
    status: R2GateStatus
    requirement: str
    observed: Dict[str, Any] = Field(default_factory=dict)


class R2GateReport(StrictModel):
    protocol_version: str = "r2-gates-v2"
    passed: bool
    gates: List[R2GateResult]


def evaluate_r2_gates(summary: Dict[str, Any]) -> R2GateReport:
    """Evaluate the preregistered R2 acceptance conditions from one summary.

    A missing comparison or metric is deliberately ``not_evaluable``.  This
    keeps a partial pilot from looking like a successful formal evaluation.
    """
    systems = summary.get("systems", {})
    comparisons = summary.get("paired_comparisons", {})
    agentic = systems.get("A1")
    no_coverage_retry = systems.get("A2")
    no_tools = systems.get("A3")
    baseline = systems.get("B3")
    gates = [
        _gac_improvement_gate(comparisons.get("A1_vs_B3")),
        _ablation_comparisons_present_gate(
            comparisons.get("A2_vs_A1"), comparisons.get("A3_vs_A1"),
        ),
        _metric_upper_bound_gate(
            "a1_failure_rate",
            agentic,
            "failure_rate",
            0.05,
            "A1 failure rate must be at or below 5%.",
        ),
        _metric_lower_bound_gate(
            "a1_tool_result_accuracy",
            agentic,
            "tool_result_accuracy",
            0.80,
            "A1 tool-task correctness must be at or above 80%.",
        ),
        _metric_upper_bound_gate(
            "a1_p95_latency",
            agentic,
            "p95_latency_seconds",
            24.0,
            "A1 P95 latency must be at or below 24 seconds.",
        ),
        _citation_precision_gate(agentic, baseline),
        _systems_present_gate(baseline, agentic, no_coverage_retry, no_tools),
    ]
    return R2GateReport(
        passed=all(gate.status == R2GateStatus.PASS for gate in gates),
        gates=gates,
    )


def _systems_present_gate(
    baseline: Optional[Dict[str, Any]],
    agentic: Optional[Dict[str, Any]],
    no_coverage_retry: Optional[Dict[str, Any]],
    no_tools: Optional[Dict[str, Any]],
) -> R2GateResult:
    present = {
        "B3": baseline is not None,
        "A1": agentic is not None,
        "A2": no_coverage_retry is not None,
        "A3": no_tools is not None,
    }
    return R2GateResult(
        name="required_systems_present",
        status=R2GateStatus.PASS if all(present.values()) else R2GateStatus.NOT_EVALUABLE,
        requirement="The report must contain B3, A1, A2, and A3.",
        observed=present,
    )


def _gac_improvement_gate(comparison: Optional[Dict[str, Any]]) -> R2GateResult:
    value = _grounded_comparison(comparison)
    if value is None:
        return _not_evaluable(
            "gac_a1_vs_b3",
            "The lower bound of A1 minus B3 GAC must be above zero.",
        )
    ci_low = value.get("ci_low")
    if not isinstance(ci_low, (int, float)):
        return _not_evaluable(
            "gac_a1_vs_b3",
            "The lower bound of A1 minus B3 GAC must be above zero.",
            value,
        )
    return R2GateResult(
        name="gac_a1_vs_b3",
        status=R2GateStatus.PASS if ci_low > 0 else R2GateStatus.FAIL,
        requirement="The lower bound of A1 minus B3 GAC must be above zero.",
        observed=value,
    )


def _ablation_comparisons_present_gate(
    coverage_comparison: Optional[Dict[str, Any]],
    tools_comparison: Optional[Dict[str, Any]],
) -> R2GateResult:
    observed = {
        "A2_vs_A1": _grounded_comparison(coverage_comparison),
        "A3_vs_A1": _grounded_comparison(tools_comparison),
    }
    return R2GateResult(
        name="ablation_comparisons_present",
        status=(
            R2GateStatus.PASS
            if all(value is not None for value in observed.values())
            else R2GateStatus.NOT_EVALUABLE
        ),
        requirement="The report must include grounded A2-vs-A1 and A3-vs-A1 ablation comparisons.",
        observed=observed,
    )


def _metric_upper_bound_gate(
    name: str,
    metrics: Optional[Dict[str, Any]],
    metric: str,
    maximum: float,
    requirement: str,
) -> R2GateResult:
    value = metrics.get(metric) if metrics is not None else None
    if not isinstance(value, (int, float)):
        return _not_evaluable(name, requirement, {metric: value})
    return R2GateResult(
        name=name,
        status=R2GateStatus.PASS if value <= maximum else R2GateStatus.FAIL,
        requirement=requirement,
        observed={metric: value, "maximum": maximum},
    )


def _metric_lower_bound_gate(
    name: str,
    metrics: Optional[Dict[str, Any]],
    metric: str,
    minimum: float,
    requirement: str,
) -> R2GateResult:
    value = metrics.get(metric) if metrics is not None else None
    if not isinstance(value, (int, float)):
        return _not_evaluable(name, requirement, {metric: value})
    return R2GateResult(
        name=name,
        status=R2GateStatus.PASS if value >= minimum else R2GateStatus.FAIL,
        requirement=requirement,
        observed={metric: value, "minimum": minimum},
    )


def _citation_precision_gate(
    agentic: Optional[Dict[str, Any]], baseline: Optional[Dict[str, Any]],
) -> R2GateResult:
    agentic_value = agentic.get("citation_precision") if agentic is not None else None
    baseline_value = baseline.get("citation_precision") if baseline is not None else None
    if not isinstance(agentic_value, (int, float)) or not isinstance(baseline_value, (int, float)):
        return _not_evaluable(
            "citation_precision_non_regression",
            "A1 citation precision may be no more than 2pp below B3.",
            {"A1": agentic_value, "B3": baseline_value},
        )
    difference = agentic_value - baseline_value
    return R2GateResult(
        name="citation_precision_non_regression",
        status=(
            R2GateStatus.PASS
            if difference >= -MATERIAL_REGRESSION_TOLERANCE
            else R2GateStatus.FAIL
        ),
        requirement="A1 citation precision may be no more than 2pp below B3.",
        observed={
            "A1": agentic_value,
            "B3": baseline_value,
            "difference": difference,
            "minimum_difference": -MATERIAL_REGRESSION_TOLERANCE,
        },
    )


def _grounded_comparison(comparison: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(comparison, dict):
        return None
    value = comparison.get("grounded_answer_completeness")
    return value if isinstance(value, dict) else None


def _not_evaluable(
    name: str,
    requirement: str,
    observed: Optional[Dict[str, Any]] = None,
) -> R2GateResult:
    return R2GateResult(
        name=name,
        status=R2GateStatus.NOT_EVALUABLE,
        requirement=requirement,
        observed=observed or {},
    )
