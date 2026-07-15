"""Derive the one-time batch-rewrite quota from judged, de-duplicated candidates."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_validator import _case_query_text, _query_similarity
from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--judgements", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--retained-output", type=Path, required=True)
    parser.add_argument("--rewrite-quota-output", type=Path, required=True)
    return parser.parse_args()


def _required_point_ids(case: BenchmarkCase) -> list[str]:
    point_ids = [point.point_id for point in case.answer_points if point.required]
    for turn in case.turns:
        point_ids.extend(point.point_id for point in turn.answer_points if point.required)
    return point_ids


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    assessments = {
        payload["case_id"]: JudgeAssessment.model_validate(payload["assessment"])
        for payload in read_jsonl(args.judgements)
    }
    if set(assessments) != {case.case_id for case in cases}:
        raise ValueError("judgements must cover exactly the candidate pool")
    retained = []
    for case in sorted(cases, key=lambda item: item.case_id):
        assessment = assessments[case.case_id]
        if not assessment.passes(_required_point_ids(case)):
            continue
        if any(
            _query_similarity(_case_query_text(case), _case_query_text(existing)) >= 0.9
            for existing in retained
        ):
            continue
        retained.append(case)
    quota = SamplingQuota.model_validate(json.loads(args.quota.read_text(encoding="utf-8")))
    available = Counter(
        (case.primary_category.value, case.language.value, case.difficulty.value)
        for case in retained
    )
    cells = []
    for cell in quota.cells:
        missing = cell.count - available[cell.key]
        if missing > 0:
            payload = cell.model_dump(mode="json")
            payload["count"] = missing
            cells.append(payload)
    write_jsonl(args.retained_output, retained)
    write_json(args.rewrite_quota_output, {"cells": cells})
    print(f"Retained {len(retained)} candidates; rewrite quota requests {sum(cell['count'] for cell in cells)}")


if __name__ == "__main__":
    main()
