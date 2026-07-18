"""Reselect a fixed review pool from frozen static-validation artifacts.

This command is for documented pre-release replacements after an audit rejection.
It deliberately reuses the original static-eligible pool and validation records,
so later validator changes cannot silently alter an already selected benchmark.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.pre_review import select_pre_review_cases
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import BenchmarkCase, ValidationRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-eligible", type=Path, required=True)
    parser.add_argument("--static-validation", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--exclude-case-id", action="append", default=[])
    parser.add_argument(
        "--previous-selection",
        type=Path,
        help="Optional prior selected-case JSONL used to export only replacement cases.",
    )
    parser.add_argument(
        "--replacement-output",
        type=Path,
        help="Output JSONL for cases newly selected relative to --previous-selection.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if bool(args.previous_selection) != bool(args.replacement_output):
        raise ValueError("--previous-selection and --replacement-output must be supplied together")
    cases = read_jsonl(args.static_eligible, BenchmarkCase)
    records = read_jsonl(args.static_validation, ValidationRecord)
    quota = SamplingQuota.model_validate(json.loads(args.quota.read_text(encoding="utf-8")))
    excluded_case_ids = sorted(set(args.exclude_case_id))
    selected, manifest = select_pre_review_cases(
        cases=[case for case in cases if case.case_id not in excluded_case_ids],
        validation_records=records,
        quota=quota,
        seed=args.seed,
        review_state="pending_automated_review",
    )
    manifest.update({
        "review_mode": "automated_only",
        "selection_basis": "frozen_static_validation_artifacts",
        "excluded_case_ids": excluded_case_ids,
        "selection_after_audit_rejections": bool(excluded_case_ids),
    })
    write_jsonl(args.output, selected)
    if args.previous_selection:
        previous = read_jsonl(args.previous_selection, BenchmarkCase)
        previous_ids = {case.case_id for case in previous}
        write_jsonl(
            args.replacement_output,
            [case for case in selected if case.case_id not in previous_ids],
        )
    write_json(args.manifest_output, manifest)
    print(
        f"Selected {len(selected)} automated-review cases from frozen static artifacts; "
        f"excluded={len(excluded_case_ids)}"
    )


if __name__ == "__main__":
    main()
