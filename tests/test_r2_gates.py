from app.evaluation.r2_gates import R2GateStatus, evaluate_r2_gates


def _summary(gac_ci_low: float = 0.01) -> dict:
    return {
        "systems": {
            "B3": {"citation_precision": 0.70},
            "A1": {
                "failure_rate": 0.02,
                "tool_result_accuracy": 0.90,
                "p95_latency_seconds": 20.0,
                "citation_precision": 0.79,
            },
            "A2": {"citation_precision": 0.78},
            "A3": {"citation_precision": 0.77},
        },
        "paired_comparisons": {
            "A1_vs_B3": {
                "grounded_answer_completeness": {
                    "mean_difference": 0.12, "ci_low": gac_ci_low, "ci_high": 0.22,
                },
            },
            "A2_vs_A1": {
                "grounded_answer_completeness": {
                    "mean_difference": -0.03, "ci_low": -0.08, "ci_high": 0.01,
                },
            },
            "A3_vs_A1": {
                "grounded_answer_completeness": {
                    "mean_difference": -0.02, "ci_low": -0.07, "ci_high": 0.02,
                },
            },
        },
    }


def test_r2_gates_pass_only_when_all_preregistered_conditions_pass():
    report = evaluate_r2_gates(_summary())

    assert report.passed is True
    assert {gate.status for gate in report.gates} == {R2GateStatus.PASS}


def test_r2_gates_fail_when_a1_does_not_improve_over_b3():
    report = evaluate_r2_gates(_summary(gac_ci_low=0.0))
    primary = next(gate for gate in report.gates if gate.name == "gac_a1_vs_b3")

    assert report.passed is False
    assert primary.status == R2GateStatus.FAIL


def test_r2_gates_do_not_treat_missing_tool_metrics_as_a_pass():
    summary = _summary()
    summary["systems"]["A1"]["tool_result_accuracy"] = None

    report = evaluate_r2_gates(summary)
    tool_gate = next(gate for gate in report.gates if gate.name == "a1_tool_result_accuracy")

    assert report.passed is False
    assert tool_gate.status == R2GateStatus.NOT_EVALUABLE
