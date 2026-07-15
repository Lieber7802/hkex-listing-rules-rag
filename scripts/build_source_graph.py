"""Build a deterministic source graph from the frozen evaluation source registry."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.source_graph import build_source_graph_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=Path("data/evaluation/source_registry/sources.jsonl"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/evaluation/source_graph"),
    )
    parser.add_argument(
        "--vector-index",
        type=Path,
        default=Path("data/indexes/vector/faiss_index.bin"),
    )
    parser.add_argument(
        "--chunk-ids",
        type=Path,
        default=Path("data/indexes/vector/chunk_ids.pkl"),
    )
    parser.add_argument("--semantic-top-k", type=int, default=10)
    parser.add_argument("--semantic-threshold", type=float, default=0.72)
    parser.add_argument("--max-semantic-edges-per-node", type=int, default=5)
    parser.add_argument(
        "--no-semantic",
        action="store_true",
        help="Skip semantic edges even when the existing vector index is available.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vector_index = None if args.no_semantic else args.vector_index
    chunk_ids = None if args.no_semantic else args.chunk_ids
    if not args.no_semantic:
        if not vector_index.is_file() or not chunk_ids.is_file():
            raise FileNotFoundError(
                "semantic graph construction requires both --vector-index and --chunk-ids"
            )
    stats = build_source_graph_files(
        source_registry_path=args.source_registry,
        output_dir=args.output_dir,
        vector_index_path=vector_index,
        chunk_ids_path=chunk_ids,
        semantic_top_k=args.semantic_top_k,
        semantic_threshold=args.semantic_threshold,
        max_semantic_edges_per_node=args.max_semantic_edges_per_node,
    )
    print(stats.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
