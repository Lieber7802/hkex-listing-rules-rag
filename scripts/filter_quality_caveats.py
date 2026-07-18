"""Filter quality-caveat disclosures to an immutable final benchmark selection."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_json
from app.evaluation.schemas import BenchmarkCase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    case_ids = {case.case_id for case in read_jsonl(args.candidates, BenchmarkCase)}
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("quality caveats input must contain an items array")
    payload["items"] = [
        item for item in items
        if isinstance(item, dict) and item.get("case_id") in case_ids
    ]
    payload["caveat_count"] = len(payload["items"])
    payload["selected_case_count"] = len(case_ids)
    write_json(args.output, payload)
    print(f"Filtered quality caveats to {len(payload['items'])} selected cases")


if __name__ == "__main__":
    main()
