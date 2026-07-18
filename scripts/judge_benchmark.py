"""Generate structured LLM-judge assessments for benchmark candidates."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_judge import LLMBenchmarkJudge
from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.schemas import BenchmarkCase
from app.evaluation.source_registry import SourceRegistry, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Persist completed assessments after this many new cases.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse valid assessments already present in --output.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Bounded number of concurrent independent judge requests.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        help="Maximum structured-output attempts per candidate.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        help="Optional JSON record of the frozen candidate input and judge settings.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    registry = SourceRegistry.load(args.source_registry)
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be at least 1")
    records_by_case_id = {}
    if args.resume and args.output.exists():
        for record in read_jsonl(args.output):
            case_id = record.get("case_id")
            assessment = record.get("assessment")
            if isinstance(case_id, str) and isinstance(assessment, dict):
                records_by_case_id[case_id] = record
    checkpoint_every = max(1, args.checkpoint_every)
    completed_since_checkpoint = 0
    failed_case_ids = []
    pending_cases = []
    for case in sorted(cases, key=lambda item: item.case_id):
        existing = records_by_case_id.get(case.case_id)
        if (
            existing
            and isinstance(existing.get("assessment"), dict)
            and existing["assessment"].get("case_hash") == case.content_hash()
        ):
            continue
        pending_cases.append(case)

    def checkpoint() -> None:
        write_jsonl(args.output, [records_by_case_id[key] for key in sorted(records_by_case_id)])
        print(f"Checkpointed {len(records_by_case_id)}/{len(cases)} judge assessments")

    def record_assessment(case: BenchmarkCase, assessment) -> None:
        nonlocal completed_since_checkpoint
        records_by_case_id[case.case_id] = {
            "case_id": case.case_id,
            "assessment": assessment.model_dump(mode="json"),
        }
        completed_since_checkpoint += 1
        if completed_since_checkpoint >= checkpoint_every:
            checkpoint()
            completed_since_checkpoint = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                LLMBenchmarkJudge(model=args.model, max_attempts=args.max_attempts).assess,
                case,
                registry,
            ): case
            for case in pending_cases
        }
        for future in as_completed(futures):
            case = futures[future]
            try:
                assessment = future.result()
            except Exception as exc:
                failed_case_ids.append(case.case_id)
                print(f"Judge failed for {case.case_id}: {exc}")
                continue
            record_assessment(case, assessment)
    records = [records_by_case_id[key] for key in sorted(records_by_case_id)]
    write_jsonl(args.output, records)
    print(
        f"Wrote {len(records)} judge assessments to {args.output}; "
        f"{len(failed_case_ids)} cases failed after retries"
    )
    if args.run_manifest:
        write_json(args.run_manifest, {
            "candidate_path": str(args.candidates),
            "candidate_sha256": sha256_file(args.candidates),
            "source_registry_path": str(args.source_registry),
            "source_registry_sha256": sha256_file(args.source_registry),
            "judge_model": args.model,
            "max_attempts": args.max_attempts,
            "workers": args.workers,
            "completed_assessments": len(records),
            "failed_case_ids": sorted(failed_case_ids),
            "judgements_sha256": sha256_file(args.output),
        })


if __name__ == "__main__":
    main()
