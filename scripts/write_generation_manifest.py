"""Write an auditable manifest for Terra-authored benchmark candidates."""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_generator import CandidateGenerationManifest
from app.evaluation.dataset_loader import read_jsonl, write_json
from app.evaluation.schemas import BenchmarkCase
from app.evaluation.source_registry import SourceRegistry, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--graph-stats", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--target-multiplier", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    if not cases:
        raise ValueError("candidates file is empty")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("candidates contain duplicate case IDs")
    if len({case.content_hash() for case in cases}) != len(cases):
        raise ValueError("candidates contain duplicate full-case content hashes")
    registry = SourceRegistry.load(args.source_registry)
    if registry.manifest is None:
        raise ValueError("source registry requires a snapshot manifest")
    models = {case.provenance.generator_model for case in cases}
    prompt_hashes = {case.provenance.generator_prompt_hash for case in cases}
    snapshot_ids = {case.provenance.source_snapshot_id for case in cases}
    snapshot_hashes = {case.provenance.source_snapshot_hash for case in cases}
    if len(models) != 1 or len(prompt_hashes) != 1:
        raise ValueError("candidates must have one generator model and prompt hash")
    if snapshot_ids != {registry.manifest.snapshot_id} or snapshot_hashes != {registry.manifest.source_sha256}:
        raise ValueError("candidate provenance does not match the frozen source snapshot")
    graph_stats = json.loads(args.graph_stats.read_text(encoding="utf-8"))
    manifest = CandidateGenerationManifest(
        generator_model=next(iter(models)),
        generator_prompt_hash=next(iter(prompt_hashes)),
        source_snapshot_id=registry.manifest.snapshot_id,
        source_snapshot_hash=registry.manifest.source_sha256,
        graph_nodes_sha256=graph_stats["nodes_sha256"],
        graph_edges_sha256=graph_stats["edges_sha256"],
        seed=args.seed,
        target_multiplier=args.target_multiplier,
        candidate_count=len(cases),
        category_counts=dict(Counter(case.primary_category.value for case in cases)),
        language_counts=dict(Counter(case.language.value for case in cases)),
        difficulty_counts=dict(Counter(case.difficulty.value for case in cases)),
        candidates_sha256=sha256_file(args.candidates),
        created_at=datetime.now(tz=timezone.utc),
    )
    write_json(args.output, manifest)
    print(f"Wrote manifest for {len(cases)} candidates to {args.output}")


if __name__ == "__main__":
    main()
