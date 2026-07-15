"""Freeze a fully approved evaluation dataset as an immutable release artifact."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl
from app.evaluation.schemas import BenchmarkCase, ValidationRecord


ARTIFACTS = {
    "benchmark": "benchmark.jsonl",
    "judgements": "judgements.jsonl",
    "human_reviews": "human_reviews.jsonl",
    "validation": "validation.jsonl",
    "source_snapshot": "source_snapshot_manifest.json",
    "source_graph": "source_graph_stats.json",
    "quota": "quota.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_wrapped_case_ids(path: Path, key: str) -> set[str]:
    records = read_jsonl(path)
    case_ids = {record.get("case_id") for record in records}
    if len(case_ids) != len(records) or not all(isinstance(case_id, str) for case_id in case_ids):
        raise ValueError(f"{path} must contain one unique case_id per record")
    if any(key not in record for record in records):
        raise ValueError(f"{path} contains a record without {key}")
    return case_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--judgements", type=Path, required=True)
    parser.add_argument("--human-reviews", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.release_dir.exists():
        raise FileExistsError(f"release directory already exists: {args.release_dir}")

    cases = read_jsonl(args.benchmark, BenchmarkCase)
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != len(cases):
        raise ValueError("benchmark contains duplicate case IDs")
    judgements = _load_wrapped_case_ids(args.judgements, "assessment")
    human_reviews = _load_wrapped_case_ids(args.human_reviews, "review")
    validations = read_jsonl(args.validation, ValidationRecord)
    validation_ids = {record.case_id for record in validations}
    if len(validation_ids) != len(validations):
        raise ValueError("validation contains duplicate case IDs")
    for label, artifact_ids in {
        "judgements": judgements,
        "human_reviews": human_reviews,
        "validation": validation_ids,
    }.items():
        if artifact_ids != case_ids:
            raise ValueError(f"{label} does not cover exactly the benchmark cases")
    if not all(record.accepted for record in validations):
        raise ValueError("cannot freeze a release with unaccepted validation records")

    input_paths = {
        "benchmark": args.benchmark,
        "judgements": args.judgements,
        "human_reviews": args.human_reviews,
        "validation": args.validation,
        "source_snapshot": args.source_snapshot,
        "source_graph": args.source_graph,
        "quota": args.quota,
    }
    for path in input_paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    args.release_dir.mkdir(parents=True)
    try:
        files = {}
        for label, source_path in input_paths.items():
            destination = args.release_dir / ARTIFACTS[label]
            shutil.copy2(source_path, destination)
            files[label] = {
                "path": destination.name,
                "sha256": _sha256(destination),
                "bytes": destination.stat().st_size,
            }
        manifest = {
            "version": args.version,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "case_count": len(cases),
            "all_cases_accepted": True,
            "source_snapshot_id": cases[0].provenance.source_snapshot_id if cases else None,
            "source_snapshot_hash": cases[0].provenance.source_snapshot_hash if cases else None,
            "files": files,
        }
        manifest_path = args.release_dir / "release_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except Exception:
        shutil.rmtree(args.release_dir, ignore_errors=True)
        raise
    print(f"Frozen {len(cases)} approved cases as {args.version} at {args.release_dir}")


if __name__ == "__main__":
    main()
