"""Merge compatible automated-review records for one frozen candidate set."""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import AutomatedReview, BenchmarkCase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review-input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def merge_reviews(
    cases: List[BenchmarkCase],
    review_paths: List[Path],
) -> List[Dict[str, object]]:
    case_hashes = {case.case_id: case.content_hash() for case in cases}
    rows: List[Dict[str, object]] = []
    seen: set[Tuple[str, str]] = set()
    covered: set[str] = set()
    for path in review_paths:
        for row in read_jsonl(path):
            case_id = row.get("case_id")
            payload = row.get("automated_review")
            if case_id not in case_hashes or not isinstance(payload, dict):
                continue
            review = AutomatedReview.model_validate(payload)
            if review.case_hash != case_hashes[case_id]:
                raise ValueError(f"automated review hash mismatch for {case_id} in {path}")
            key = (case_id, review.reviewer_id)
            if key in seen:
                raise ValueError(f"duplicate reviewer {review.reviewer_id} for {case_id}")
            seen.add(key)
            covered.add(case_id)
            rows.append({
                "case_id": case_id,
                "automated_review": review.model_dump(mode="json"),
            })
    missing = sorted(set(case_hashes) - covered)
    if missing:
        raise ValueError(f"automated reviews are missing selected cases: {missing}")
    return sorted(rows, key=lambda row: (
        str(row["case_id"]),
        str(row["automated_review"]["reviewer_id"]),
    ))


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    merged = merge_reviews(cases, args.review_input)
    write_jsonl(args.output, merged)
    print(f"Merged {len(merged)} automated review records for {len(cases)} selected cases")


if __name__ == "__main__":
    main()
