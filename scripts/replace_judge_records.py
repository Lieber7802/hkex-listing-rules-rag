"""Replace selected wrapped judge records while preserving complete assessment coverage."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment


def _record(
    payload: dict,
    cases_by_id: dict[str, BenchmarkCase],
    require_current_hash: bool = True,
) -> dict:
    case_id = payload.get("case_id")
    if not isinstance(case_id, str) or "assessment" not in payload:
        raise ValueError("judge records require case_id and assessment")
    case = cases_by_id.get(case_id)
    if case is None:
        raise ValueError(f"judge record references unknown case {case_id}")
    assessment = JudgeAssessment.model_validate(payload["assessment"])
    if require_current_hash and assessment.case_hash != case.content_hash():
        raise ValueError(f"judge assessment hash mismatch for {case_id}")
    return {"case_id": case_id, "assessment": assessment.model_dump(mode="json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--replacements-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    cases_by_id = {case.case_id: case for case in cases}
    replacements = {}
    for path in sorted(args.replacements_dir.glob("part_*.jsonl")):
        for payload in read_jsonl(path):
            record = _record(payload, cases_by_id)
            if record["case_id"] in replacements:
                raise ValueError(f"duplicate replacement assessment for {record['case_id']}")
            replacements[record["case_id"]] = record
    if not replacements:
        raise ValueError("no replacement judge records found")
    base = {}
    for payload in read_jsonl(args.base):
        record = _record(payload, cases_by_id, require_current_hash=False)
        case_id = record["case_id"]
        if case_id in base:
            raise ValueError(f"duplicate base assessment for {case_id}")
        if (
            record["assessment"]["case_hash"] != cases_by_id[case_id].content_hash()
            and case_id not in replacements
        ):
            raise ValueError(f"stale base assessment has no replacement for {case_id}")
        base[case_id] = record
    missing = sorted(set(cases_by_id) - (set(base) | set(replacements)))
    if missing:
        raise ValueError(f"missing assessments for {len(missing)} cases; first IDs: {missing[:10]}")
    output = [replacements.get(case.case_id, base[case.case_id]) for case in cases]
    write_jsonl(args.output, output)
    print(f"Replaced {len(replacements)} of {len(output)} judge assessments in {args.output}")


if __name__ == "__main__":
    main()
