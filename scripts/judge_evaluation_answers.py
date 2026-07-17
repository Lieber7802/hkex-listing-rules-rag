"""Judge case-level evaluation answers against frozen answer-point evidence mappings."""

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.answer_judge import GroundedAnswerJudge
from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow, GroundedAnswerAssessment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["deterministic", "llm"], default="deterministic")
    parser.add_argument("--model")
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=25,
        help="Persist completed assessments after this many newly judged rows.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse matching assessments already present in --output.",
    )
    args = parser.parse_args()

    cases = read_jsonl(args.benchmark, BenchmarkCase)
    case_map = {case.case_id: case for case in cases}
    rows = [
        row
        for path in args.results
        for row in read_jsonl(path, EvaluationRunRow)
        if row.row_type.value in {"single_turn", "aggregate"} and row.case_id in case_map
    ]
    expected_keys = {(row.system, row.case_id) for row in rows}
    if len(expected_keys) != len(rows):
        raise ValueError("results contain duplicate case-level rows for a system")

    judge = GroundedAnswerJudge(backend=args.backend, model=args.model)
    expected_backend = (
        "deterministic"
        if args.backend == "deterministic"
        else f"llm:{judge.model}"
    )
    assessments_by_key = {}
    if args.resume and args.output.exists():
        for assessment in read_jsonl(args.output, GroundedAnswerAssessment):
            assessments_by_key[(assessment.system, assessment.case_id)] = assessment

    checkpoint_every = max(1, args.checkpoint_every)
    completed_since_checkpoint = 0
    for row in sorted(rows, key=lambda item: (item.system, item.case_id)):
        key = (row.system, row.case_id)
        existing = assessments_by_key.get(key)
        answer_hash = hashlib.sha256(row.answer.encode("utf-8")).hexdigest()
        if (
            existing is not None
            and existing.answer_hash == answer_hash
            and existing.judge_backend == expected_backend
        ):
            continue
        assessments_by_key[key] = judge.assess(case_map[row.case_id], row)
        completed_since_checkpoint += 1
        if completed_since_checkpoint >= checkpoint_every:
            _write_expected_assessments(
                args.output, assessments_by_key, expected_keys, require_complete=False,
            )
            completed_since_checkpoint = 0
            print(f"Checkpointed {len(assessments_by_key)}/{len(rows)} grounded answer assessments")

    _write_expected_assessments(args.output, assessments_by_key, expected_keys)
    print(f"Wrote {len(expected_keys)} grounded answer assessments to {args.output}")


def _write_expected_assessments(
    output: Path,
    assessments_by_key: dict[tuple[str, str], GroundedAnswerAssessment],
    expected_keys: set[tuple[str, str]],
    require_complete: bool = True,
) -> None:
    missing = expected_keys - set(assessments_by_key)
    if missing and require_complete:
        raise ValueError(f"missing grounded answer assessments: {sorted(missing)}")
    write_jsonl(output, [
        assessments_by_key[key]
        for key in sorted(expected_keys & set(assessments_by_key))
    ])


if __name__ == "__main__":
    main()
