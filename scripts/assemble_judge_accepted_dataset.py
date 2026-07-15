"""Assemble a final benchmark from layered candidates that passed independent judging."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment


def _required_point_ids(case: BenchmarkCase) -> list[str]:
    point_ids = [point.point_id for point in case.answer_points if point.required]
    for turn in case.turns:
        point_ids.extend(point.point_id for point in turn.answer_points if point.required)
    return point_ids


def _load_assessments(path: Path) -> dict[str, JudgeAssessment]:
    assessments: dict[str, JudgeAssessment] = {}
    for payload in read_jsonl(path):
        case_id = payload.get("case_id")
        if not isinstance(case_id, str) or "assessment" not in payload:
            raise ValueError(f"{path} contains a record without case_id and assessment")
        if case_id in assessments:
            raise ValueError(f"{path} contains duplicate assessment for {case_id}")
        assessments[case_id] = JudgeAssessment.model_validate(payload["assessment"])
    return assessments


def _add_passing_cases(
    selected: dict[str, BenchmarkCase],
    selected_assessments: dict[str, JudgeAssessment],
    candidates_path: Path,
    assessments_path: Path,
) -> tuple[int, int]:
    candidates = read_jsonl(candidates_path, BenchmarkCase)
    assessments = _load_assessments(assessments_path)
    candidate_ids = {case.case_id for case in candidates}
    missing_assessments = candidate_ids - set(assessments)
    if missing_assessments:
        raise ValueError(
            f"assessments are missing {len(missing_assessments)} candidates in {candidates_path}: "
            f"{sorted(missing_assessments)[:10]}"
        )
    passed = 0
    for case in candidates:
        assessment = assessments[case.case_id]
        if assessment.case_hash != case.content_hash():
            raise ValueError(f"assessment hash mismatch for {case.case_id}")
        if assessment.judge_model == case.provenance.generator_model:
            raise ValueError(f"judge is not independent for {case.case_id}")
        if not assessment.passes(_required_point_ids(case)):
            continue
        selected[case.case_id] = case
        selected_assessments[case.case_id] = assessment
        passed += 1
    return len(candidates), passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-candidates", type=Path, required=True)
    parser.add_argument("--base-assessments", type=Path, required=True)
    parser.add_argument("--layer-candidates", type=Path, action="append", default=[])
    parser.add_argument("--layer-assessments", type=Path, action="append", default=[])
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--output-candidates", type=Path, required=True)
    parser.add_argument("--output-assessments", type=Path, required=True)
    args = parser.parse_args()
    if len(args.layer_candidates) != len(args.layer_assessments):
        raise ValueError("each layer candidate file needs one matching assessment file")

    selected: dict[str, BenchmarkCase] = {}
    selected_assessments: dict[str, JudgeAssessment] = {}
    layer_stats = [
        _add_passing_cases(
            selected,
            selected_assessments,
            args.base_candidates,
            args.base_assessments,
        )
    ]
    for candidates_path, assessments_path in zip(args.layer_candidates, args.layer_assessments):
        layer_stats.append(
            _add_passing_cases(selected, selected_assessments, candidates_path, assessments_path)
        )

    quota = SamplingQuota.model_validate(json.loads(args.quota.read_text(encoding="utf-8")))
    observed = Counter(
        (case.primary_category.value, case.language.value, case.difficulty.value)
        for case in selected.values()
    )
    expected = {cell.key: cell.count for cell in quota.cells}
    if observed != expected:
        missing = {"|".join(key): expected[key] - observed.get(key, 0) for key in expected if observed.get(key, 0) < expected[key]}
        excess = {"|".join(key): observed[key] - expected.get(key, 0) for key in observed if observed[key] > expected.get(key, 0)}
        raise ValueError(f"final joint quota mismatch; missing={missing}, excess={excess}")

    cases = [selected[case_id] for case_id in sorted(selected)]
    if len({case.content_hash() for case in cases}) != len(cases):
        raise ValueError("final dataset contains duplicate full-case content hashes")
    assessments = [
        {"case_id": case.case_id, "assessment": selected_assessments[case.case_id].model_dump(mode="json")}
        for case in cases
    ]
    write_jsonl(args.output_candidates, cases)
    write_jsonl(args.output_assessments, assessments)
    stats = ", ".join(f"{passed}/{total}" for total, passed in layer_stats)
    print(f"Assembled {len(cases)} judge-accepted cases; layer pass counts: {stats}")


if __name__ == "__main__":
    main()
