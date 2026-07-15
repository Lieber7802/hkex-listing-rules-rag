from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from app.evaluation.dataset_loader import write_json
from app.evaluation.metrics import evaluate_rows
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["system"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_report(rows: Iterable[EvaluationRunRow], cases: Iterable[BenchmarkCase], output_dir: Path) -> dict:
    rows, cases, output_dir = list(rows), list(cases), Path(output_dir)
    summary = evaluate_rows(rows, cases)
    summary_rows = [{"system": system, **metrics} for system, metrics in summary["systems"].items()]
    _write_csv(output_dir / "summary.csv", summary_rows)
    _write_csv(output_dir / "paired_comparisons.csv", [
        {"comparison": name, **values["paired_bootstrap"], **{
            f"mcnemar_{key}": value for key, value in values["mcnemar"].items()
        }} for name, values in summary.get("paired_comparisons", {}).items()
    ])

    case_map = {case.case_id: case for case in cases}
    for attribute, filename in (("primary_category", "category_breakdown.csv"), ("language", "language_breakdown.csv"), ("difficulty", "difficulty_breakdown.csv")):
        buckets = defaultdict(lambda: {"cases": 0, "successes": 0})
        for row in rows:
            if row.row_type.value not in {"single_turn", "aggregate"}:
                continue
            value = getattr(case_map[row.case_id], attribute)
            key = (row.system, value.value if hasattr(value, "value") else str(value))
            buckets[key]["cases"] += 1
            buckets[key]["successes"] += int(not row.error and bool(row.answer.strip()))
        _write_csv(output_dir / filename, [
            {"system": system, attribute: value, **data, "success_rate": data["successes"] / data["cases"]}
            for (system, value), data in sorted(buckets.items())
        ])
    buckets = defaultdict(lambda: {"cases": 0, "successes": 0})
    for row in rows:
        if row.row_type.value not in {"single_turn", "aggregate"}:
            continue
        key = (row.system, case_map[row.case_id].case_type.value)
        buckets[key]["cases"] += 1
        buckets[key]["successes"] += int(not row.error and bool(row.answer.strip()))
    _write_csv(output_dir / "case_type_breakdown.csv", [
        {"system": system, "case_type": value, **data, "success_rate": data["successes"] / data["cases"]}
        for (system, value), data in sorted(buckets.items())
    ])

    write_json(output_dir / "metric_readiness.json", summary["readiness"])
    common_cases = [case for case in cases if not case.expected_tool_calls and not case.turns]
    agentic_cases = [case for case in cases if case.expected_tool_calls or case.turns]
    for label, subset in (("common_capability_summary.csv", common_cases), ("agentic_capability_summary.csv", agentic_cases)):
        subset_ids = {case.case_id for case in subset}
        subset_rows = [row for row in rows if row.case_id in subset_ids]
        subset_summary = evaluate_rows(subset_rows, subset)
        _write_csv(output_dir / label, [
            {"system": system, **metrics} for system, metrics in subset_summary["systems"].items()
        ])
    lines = ["# Evaluation Report", "", "## Overall"]
    for item in summary_rows:
        lines.append(f"- {item['system']}: cases={item['case_count']}, answer-point coverage={item['answer_point_coverage']}, failure rate={item['failure_rate']}")
    lines.extend(["", "## Metric Readiness"])
    for name, value in summary["readiness"].items():
        lines.append(f"- {name}: {'ready' if value['ready'] else 'not ready'}")
    lines.extend(["", "## Paired Comparisons"])
    for name, values in summary.get("paired_comparisons", {}).items():
        bootstrap = values["paired_bootstrap"]
        mcnemar = values["mcnemar"]
        lines.append(
            f"- {name}: mean difference={bootstrap['mean_difference']:.4f}, "
            f"95% CI=[{bootstrap['ci_low']:.4f}, {bootstrap['ci_high']:.4f}], "
            f"McNemar p={mcnemar['exact_two_sided_p_value']:.4f}"
        )
    lines.extend(["", "## Not Reported"])
    lines.extend(f"- {metric}: N/A until its evidence/readiness contract is satisfied" for metric in summary["not_reported_metrics"])
    (output_dir / "evaluation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return summary
