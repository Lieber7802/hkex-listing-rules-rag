"""Generate structured LLM-judge assessments for benchmark candidates."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_judge import LLMBenchmarkJudge
from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase
from app.evaluation.source_registry import SourceRegistry


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    registry = SourceRegistry.load(args.source_registry)
    judge = LLMBenchmarkJudge(model=args.model)
    records_by_case_id = {}
    if args.resume and args.output.exists():
        for record in read_jsonl(args.output):
            case_id = record.get("case_id")
            assessment = record.get("assessment")
            if isinstance(case_id, str) and isinstance(assessment, dict):
                records_by_case_id[case_id] = record
    checkpoint_every = max(1, args.checkpoint_every)
    completed_since_checkpoint = 0
    for case in sorted(cases, key=lambda item: item.case_id):
        existing = records_by_case_id.get(case.case_id)
        if existing and existing["assessment"].get("case_hash") == case.content_hash():
            continue
        assessment = judge.assess(case, registry)
        records_by_case_id[case.case_id] = {
            "case_id": case.case_id,
            "assessment": assessment.model_dump(mode="json"),
        }
        completed_since_checkpoint += 1
        if completed_since_checkpoint >= checkpoint_every:
            write_jsonl(args.output, [records_by_case_id[key] for key in sorted(records_by_case_id)])
            completed_since_checkpoint = 0
            print(f"Checkpointed {len(records_by_case_id)}/{len(cases)} judge assessments")
    records = [records_by_case_id[key] for key in sorted(records_by_case_id)]
    write_jsonl(args.output, records)
    print(f"Wrote {len(records)} judge assessments to {args.output}")


if __name__ == "__main__":
    main()
