"""Replace selected BenchmarkCase records while preserving complete case coverage."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--replacements-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = read_jsonl(args.base, BenchmarkCase)
    by_id = {case.case_id: case for case in base}
    replacements = {}
    for path in sorted(args.replacements_dir.glob("part_*.jsonl")):
        for case in read_jsonl(path, BenchmarkCase):
            if case.case_id not in by_id:
                raise ValueError(f"replacement references unknown case {case.case_id}")
            if case.case_id in replacements:
                raise ValueError(f"duplicate replacement for {case.case_id}")
            replacements[case.case_id] = case
    if not replacements:
        raise ValueError("no replacement cases found")
    output = [replacements.get(case.case_id, case) for case in base]
    if len({case.case_id for case in output}) != len(output):
        raise ValueError("replacement produced duplicate case IDs")
    write_jsonl(args.output, output)
    print(f"Replaced {len(replacements)} of {len(output)} candidates in {args.output}")


if __name__ == "__main__":
    main()
