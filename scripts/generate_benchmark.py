"""Generate source-grounded benchmark candidates from the frozen source graph."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_generator import generate_candidate_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=Path("data/evaluation/source_registry/sources.jsonl"),
    )
    parser.add_argument(
        "--graph-edges",
        type=Path,
        default=Path("data/evaluation/source_graph/edges.jsonl"),
    )
    parser.add_argument(
        "--quota",
        type=Path,
        default=Path("app/evaluation/default_benchmark_quota.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/evaluation/benchmark_candidates.jsonl"),
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=Path("data/evaluation/benchmark_generation_manifest.json"),
    )
    parser.add_argument("--target-multiplier", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--case-id-prefix", default="terra")
    parser.add_argument(
        "--reference-benchmark",
        type=Path,
        help="Exclude multi-source combinations already used by a frozen earlier release.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_candidate_files(
        source_registry_path=args.source_registry,
        graph_edges_path=args.graph_edges,
        quota_path=args.quota,
        output_path=args.output,
        manifest_path=args.manifest_output,
        target_multiplier=args.target_multiplier,
        seed=args.seed,
        case_id_prefix=args.case_id_prefix,
        reference_benchmark_path=args.reference_benchmark,
    )
    print(manifest.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
