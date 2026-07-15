"""Build the evaluation source registry and frozen corpus snapshot manifest."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.source_registry import build_source_registry_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("data/indexes/vector/chunks.json"),
        help="Input chunks JSON array",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/evaluation/source_registry"),
    )
    parser.add_argument(
        "--snapshot-date",
        type=date.fromisoformat,
        default=date.today(),
        help="Current-rules snapshot date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--metadata-overrides",
        type=Path,
        help="Optional JSON object keyed by chunk_id",
    )
    parser.add_argument("--min-text-chars", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overrides = None
    if args.metadata_overrides:
        with args.metadata_overrides.open("r", encoding="utf-8") as handle:
            overrides = json.load(handle)
        if not isinstance(overrides, dict):
            raise ValueError("metadata overrides must be a JSON object keyed by chunk_id")
    manifest = build_source_registry_file(
        chunks_path=args.chunks,
        output_dir=args.output_dir,
        snapshot_date=args.snapshot_date,
        metadata_overrides=overrides,
        min_text_chars=args.min_text_chars,
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
