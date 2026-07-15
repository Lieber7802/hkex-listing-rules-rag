"""Run the frozen benchmark against B3, A1, A2 and A3."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.evaluation.execution import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--index-path", type=Path, default=settings.indexes_dir)
    parser.add_argument("--output-dir", type=Path, default=Path("data/evaluation/runs"))
    parser.add_argument("--release-manifest", type=Path)
    parser.add_argument("--allow-unfrozen", action="store_true", help="Allow pilot/development data without a release manifest")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--systems", nargs="+", choices=["B3", "A1", "A2", "A3"], default=["B3", "A1", "A2", "A3"])
    parser.add_argument("--run-id")
    args = parser.parse_args()
    manifest = args.release_manifest or (args.benchmark.parent / "release_manifest.json")
    if not args.allow_unfrozen and not manifest.is_file():
        raise SystemExit("A release manifest is required for formal evaluation; use --allow-unfrozen only for pilot runs.")
    paths = run_experiment(
        args.benchmark, args.output_dir, args.source_snapshot, args.index_path,
        args.systems, args.run_id, manifest if manifest.is_file() else None,
        args.timeout_seconds, args.max_retries,
    )
    for system, path in paths.items():
        print(f"{system}: {path}")


if __name__ == "__main__":
    main()
