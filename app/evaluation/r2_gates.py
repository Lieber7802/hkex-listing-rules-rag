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
    protocol_version: str = "r2-gates-v1"
    passed: bool
    gates: List[R2GateResult]


def evaluate_r2_gates(summary: Dict[str, Any]) -> R2GateReport:
    """Evaluate the preregistered R2 acceptance conditions from one summary.

    A missing comparison or metric is deliberately ``not_evaluable``.  This
    keeps a partial pilot from looking like a successful formal evaluation.
    """
    systems = summary.get("systems", {})
    comparisons = summary.get("paired_comparisons", {})
    new = systems.get("A1-new")
    legacy = systems.get("A1-legacy")
    baseline = systems.get("B3")
    gates = [
        _gac_improvement_gate(comparisons.get("A1-new_vs_B3")),
        _r2_attribution_gate(comparisons.get("A1-new_vs_A1-legacy")),
        _metric_upper_bound_gate(
            "a1_new_failure_rate",
            new,
            "failure_rate",
            0.05,
            "A1-new failure rate must be at or below 5%.",
        ),
        _metric_lower_bound_gate(
            "a1_new_tool_result_accuracy",
            new,
            "tool_result_accuracy",
            0.80,
            "A1-new tool-task correctness must be at or above 80%.",
        ),
        _metric_upper_bound_gate(
            "a1_new_p95_latency",
            new,
            "p95_latency_seconds",
            24.0,
            "A1-new P95 latency must be at or below 24 seconds.",
        ),
        _citation_precision_gate(new, legacy),
        _systems_present_gate(baseline, legacy, new),
    ]
    return R2GateReport(
        passed=all(gate.status == R2GateStatus.PASS for gate in gates),
        gates=gates,
    )


def _systems_present_gate(
    baseline: Optional[Dict[str, Any]],
    legacy: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]],
) -> R2GateResult:
    present = {
        "B3": baseline is not None,
        "A1-legacy": legacy is not None,
        "A1-new": new is not None,
    }
    return R2GateResult(
        name="required_systems_present",
        status=R2GateStatus.PASS if all(present.values()) else R2GateStatus.NOT_EVALUABLE,
        requirement="The report must contain B3, A1-legacy, and A1-new.",
        observed=present,
    )


def _gac_improvement_gate(comparison: Optional[Dict[str, Any]]) -> R2GateResult:
    value = _grounded_comparison(comparison)
    if value is None:
        return _not_evaluable(
            "gac_a1_new_vs_b3",
            "The lower bound of A1-new minus B3 GAC must be above zero.",
        )
    ci_low = value.get("ci_low")
    if not isinstance(ci_low, (int, float)):
        return _not_evaluable(
            "gac_a1_new_vs_b3",
            "The lower bound of A1-new minus B3 GAC must be above zero.",
            value,
        )
    return R2GateResult(
        name="gac_a1_new_vs_b3",
        status=R2GateStatus.PASS if ci_low > 0 else R2GateStatus.FAIL,
        requirement="The lower bound of A1-new minus B3 GAC must be above zero.",
        observed=value,
    )


def _r2_attribution_gate(comparison: Optional[Dict[str, Any]]) -> R2GateResult:
    value = _grounded_comparison(comparison)
    if value is None:
        return _not_evaluable(
            "gac_a1_new_vs_a1_legacy",
            "A1-new minus A1-legacy GAC must be at least +5pp and its lower CI must be no worse than -2pp.",
        )
    mean, ci_low = value.get("mean_difference"), value.get("ci_low")
    if not isinstance(mean, (int, float)) or not isinstance(ci_low, (int, float)):
        return _not_evaluable(
            "gac_a1_new_vs_a1_legacy",
            "A1-new minus A1-legacy GAC must be at least +5pp and its lower CI must be no worse than -2pp.",
            value,
        )
    return R2GateResult(
        name="gac_a1_new_vs_a1_legacy",
        status=(
            R2GateStatus.PASS
            if mean >= 0.05 and ci_low >= -MATERIAL_REGRESSION_TOLERANCE
            else R2GateStatus.FAIL
        ),
        requirement="A1-new minus A1-legacy GAC must be at least +5pp and its lower CI must be no worse than -2pp.",
        observed=value,
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
    new: Optional[Dict[str, Any]], legacy: Optional[Dict[str, Any]],
) -> R2GateResult:
    new_value = new.get("citation_precision") if new is not None else None
    legacy_value = legacy.get("citation_precision") if legacy is not None else None
    if not isinstance(new_value, (int, float)) or not isinstance(legacy_value, (int, float)):
        return _not_evaluable(
            "citation_precision_non_regression",
            "A1-new citation precision may be no more than 2pp below A1-legacy.",
            {"A1-new": new_value, "A1-legacy": legacy_value},
        )
    difference = new_value - legacy_value
    return R2GateResult(
        name="citation_precision_non_regression",
        status=(
            R2GateStatus.PASS
            if difference >= -MATERIAL_REGRESSION_TOLERANCE
            else R2GateStatus.FAIL
        ),
        requirement="A1-new citation precision may be no more than 2pp below A1-legacy.",
        observed={
            "A1-new": new_value,
            "A1-legacy": legacy_value,
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
