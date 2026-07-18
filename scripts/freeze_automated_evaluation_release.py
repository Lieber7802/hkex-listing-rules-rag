"""Freeze an evaluation release whose approval path is explicitly automated-only."""

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
from app.evaluation.r2_protocol import BenchmarkIsolationReport
from app.evaluation.schemas import AutomatedValidationRecord, BenchmarkCase


ARTIFACTS = {
    "benchmark": "benchmark.jsonl",
    "judgements": "judgements.jsonl",
    "automated_reviews": "automated_reviews.jsonl",
    "automated_validation": "automated_validation.jsonl",
    "source_snapshot": "source_snapshot_manifest.json",
    "source_graph": "source_graph_stats.json",
    "quota": "quota.json",
    "r2_isolation": "r2_isolation_report.json",
    "audit_history": "automated_audit_history.json",
    "quality_caveats": "quality_caveats.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_wrapped_case_ids(
    path: Path,
    key: str,
    *,
    allow_multiple_per_case: bool = False,
) -> set[str]:
    records = read_jsonl(path)
    case_ids = {record.get("case_id") for record in records}
    if not case_ids or not all(isinstance(case_id, str) for case_id in case_ids):
        raise ValueError(f"{path} must contain non-empty string case_id values")
    if not allow_multiple_per_case and len(case_ids) != len(records):
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
    parser.add_argument("--automated-reviews", type=Path, required=True)
    parser.add_argument("--automated-validation", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--r2-isolation-report", type=Path, required=True)
    parser.add_argument(
        "--audit-history",
        type=Path,
        required=True,
        help="Documented automated-audit decisions and any pre-release replacements.",
    )
    parser.add_argument(
        "--quality-caveats",
        type=Path,
        required=True,
        help="Required disclosure artifact for known automated-audit quality caveats.",
    )
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
    reviews = _load_wrapped_case_ids(
        args.automated_reviews,
        "automated_review",
        allow_multiple_per_case=True,
    )
    validations = read_jsonl(args.automated_validation, AutomatedValidationRecord)
    validation_ids = {record.case_id for record in validations}
    if len(validation_ids) != len(validations):
        raise ValueError("automated validation contains duplicate case IDs")
    for label, artifact_ids in {
        "judgements": judgements,
        "automated_reviews": reviews,
        "automated_validation": validation_ids,
    }.items():
        if artifact_ids != case_ids:
            raise ValueError(f"{label} does not cover exactly the benchmark cases")
    if not all(record.accepted for record in validations):
        raise ValueError("cannot freeze an automated release with unaccepted validation records")

    isolation = BenchmarkIsolationReport.model_validate(
        json.loads(args.r2_isolation_report.read_text(encoding="utf-8"))
    )
    if not isolation.passed:
        raise ValueError("cannot freeze an R2 release with a failed isolation report")
    quality_caveats = json.loads(args.quality_caveats.read_text(encoding="utf-8"))
    if quality_caveats.get("review_mode") != "automated_only":
        raise ValueError("quality caveats must be explicitly marked automated_only")
    caveat_items = quality_caveats.get("items")
    if not isinstance(caveat_items, list):
        raise ValueError("quality caveats must contain an items array")
    input_paths = {
        "benchmark": args.benchmark,
        "judgements": args.judgements,
        "automated_reviews": args.automated_reviews,
        "automated_validation": args.automated_validation,
        "source_snapshot": args.source_snapshot,
        "source_graph": args.source_graph,
        "quota": args.quota,
        "r2_isolation": args.r2_isolation_report,
        "audit_history": args.audit_history,
        "quality_caveats": args.quality_caveats,
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
            "review_mode": "automated_only",
            "human_review_status": "not_performed",
            "automated_checks_complete": True,
            "quality_caveat_count": len(caveat_items),
            "paper_reporting_restriction": (
                "This release was validated by automated checks and automated agents only; "
                "it must not be reported as human expert-reviewed. Any quality caveats "
                "included in this release must be disclosed with reported results."
            ),
            "automated_audit_history": ARTIFACTS["audit_history"],
            "source_snapshot_id": cases[0].provenance.source_snapshot_id if cases else None,
            "source_snapshot_hash": cases[0].provenance.source_snapshot_hash if cases else None,
            "files": files,
        }
        (args.release_dir / "release_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except Exception:
        shutil.rmtree(args.release_dir, ignore_errors=True)
        raise
    print(
        f"Frozen {len(cases)} automated-only cases as {args.version} at {args.release_dir}; "
        "no human expert review was performed"
    )


if __name__ == "__main__":
    main()
