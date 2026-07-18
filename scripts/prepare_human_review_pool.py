"""Validate non-human benchmark gates and select a fixed human-review pool."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_validator import BenchmarkValidator
from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.pre_review import select_pre_review_cases, static_checks_pass
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment
from app.evaluation.source_registry import SourceRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--judge-assessments", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--exclude-case-id",
        action="append",
        default=[],
        help="Exclude a statically valid candidate after a documented pre-release audit rejection.",
    )
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--static-eligible-output", type=Path, required=True)
    parser.add_argument("--review-candidates-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument(
        "--review-mode",
        choices=("human", "automated_only"),
        default="human",
        help="Select human review (default) or explicitly automated-only review metadata.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    judges = {
        row["case_id"]: JudgeAssessment.model_validate(row["assessment"])
        for row in read_jsonl(args.judge_assessments)
    }
    quota = SamplingQuota.model_validate(json.loads(args.quota.read_text(encoding="utf-8")))
    validator = BenchmarkValidator(SourceRegistry.load(args.source_registry))

    records = []
    static_eligible = []
    for case in sorted(cases, key=lambda item: item.case_id):
        record = validator.validate_case(
            case,
            accepted_cases=static_eligible,
            judge_assessment=judges.get(case.case_id),
        )
        records.append(record)
        if static_checks_pass(record):
            static_eligible.append(case)

    review_state = (
        "pending_human_approval"
        if args.review_mode == "human"
        else "pending_automated_review"
    )
    excluded_case_ids = sorted(set(args.exclude_case_id))
    eligible_after_exclusions = [
        case for case in static_eligible
        if case.case_id not in excluded_case_ids
    ]
    selected, manifest = select_pre_review_cases(
        eligible_after_exclusions,
        records,
        quota,
        args.seed,
        review_state=review_state,
    )
    manifest["review_mode"] = args.review_mode
    manifest["excluded_case_ids"] = excluded_case_ids
    manifest["selection_after_audit_rejections"] = bool(excluded_case_ids)
    write_jsonl(args.validation_output, records)
    write_jsonl(args.static_eligible_output, static_eligible)
    write_jsonl(args.review_candidates_output, selected)
    write_json(args.manifest_output, manifest)
    print(
        f"Prepared {len(selected)} {args.review_mode} review candidates from "
        f"{len(eligible_after_exclusions)} statically eligible cases"
    )


if __name__ == "__main__":
    main()
