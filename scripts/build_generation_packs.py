"""Build source-grounded generation packs for Terra-authored benchmark cases."""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import BenchmarkCase
from app.evaluation.source_registry import SourceRegistry, normalize_source_path


PROMPT = (
    "Author a natural, source-grounded HKEX BenchmarkCase. Gold answer points must be concise "
    "conclusions that answer the query, not source excerpts. Preserve exact evidence and ruleset identity."
)
PROMPT_HASH = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
PRECISE_RULE = re.compile(r"^\d{1,2}[A-Z]?(?:\.\d+[A-Z]?)$", re.IGNORECASE)
SCENARIO_BY_CATEGORY = {
    "obligation_summary": "disclosure_obligation",
    "procedure_flow": "procedure_flow",
    "size_test_calculation": "size_test",
    "tool_chain": "notifiable_transaction",
}
PAIRED_CATEGORIES = {"comparison_multi_hop", "multi_turn_follow_up"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-registry", type=Path, default=Path("data/evaluation/source_registry/sources.jsonl"))
    parser.add_argument("--nodes", type=Path, default=Path("data/evaluation/source_graph/nodes.jsonl"))
    parser.add_argument("--edges", type=Path, default=Path("data/evaluation/source_graph/edges.jsonl"))
    parser.add_argument("--quota", type=Path, default=Path("app/evaluation/default_benchmark_quota.json"))
    parser.add_argument("--target-multiplier", type=int, default=2)
    parser.add_argument("--exclude-sources-from", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--prefix", default="full")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _eligible_sources(registry: SourceRegistry) -> set[str]:
    return {
        record.chunk_id
        for record in registry.records
        if record.eligible_main_benchmark
        and "/rules/" in normalize_source_path(record.source_path)
        and record.ruleset.value in {"main_board", "gem"}
        and record.rule_number
        and PRECISE_RULE.fullmatch(record.rule_number.strip())
    }


def _connected_pairs(registry: SourceRegistry, source_ids: set[str], edges: list[dict]) -> list[tuple[str, str, dict]]:
    pairs = []
    for edge in edges:
        if edge["edge_type"] not in {"rule_reference", "same_scenario", "semantic_similarity"}:
            continue
        left = edge["src"].removeprefix("chunk:")
        right = edge["dst"].removeprefix("chunk:")
        if (
            left in source_ids
            and right in source_ids
            and registry.require(left).rule_number != registry.require(right).rule_number
        ):
            pairs.append((left, right, edge))
    return sorted(pairs, key=lambda item: (item[0], item[1], item[2]["edge_type"]))


def _source_payload(registry: SourceRegistry, source_id: str) -> dict:
    source = registry.require(source_id)
    return {
        "chunk_id": source.chunk_id,
        "ruleset": source.ruleset.value,
        "rule_number": source.rule_number,
        "chapter": source.chapter,
        "section_title": source.section_title,
        "source_path": source.source_path,
        "text": source.text,
    }


def main() -> None:
    args = parse_args()
    if args.target_multiplier < 1:
        raise ValueError("target multiplier must be at least one")
    registry = SourceRegistry.load(args.source_registry)
    nodes = {row["chunk_id"]: row for row in read_jsonl(args.nodes)}
    quota = SamplingQuota.model_validate(json.loads(args.quota.read_text(encoding="utf-8")))
    source_ids = _eligible_sources(registry)
    if args.exclude_sources_from:
        excluded_source_ids = {
            source_id
            for case in read_jsonl(args.exclude_sources_from, BenchmarkCase)
            for source_id in case.source_chunk_ids
        }
        source_ids -= excluded_source_ids
    if not source_ids:
        raise RuntimeError("no eligible sources remain after applying exclusions")
    scenario_sources = defaultdict(list)
    for source_id in source_ids:
        for scenario in nodes[source_id]["scenarios"]:
            scenario_sources[scenario].append(source_id)
    for values in scenario_sources.values():
        values.sort()
    all_sources = sorted(source_ids)
    pairs = _connected_pairs(registry, source_ids, read_jsonl(args.edges))
    if len(pairs) < 20:
        raise RuntimeError("not enough precise connected rule pairs for pack generation")

    records = []
    ordinal = 0
    for cell in sorted(quota.cells, key=lambda item: item.key):
        category, language, difficulty = cell.key
        for replicate in range(cell.count * args.target_multiplier):
            if category in PAIRED_CATEGORIES:
                left, right, connection = pairs[(ordinal * 97 + args.seed) % len(pairs)]
                selected = [left, right]
            else:
                pool = scenario_sources.get(SCENARIO_BY_CATEGORY.get(category), all_sources)
                selected = [pool[(ordinal * 101 + args.seed) % len(pool)]]
                connection = None
            case_id = f"{args.prefix}-{category}-{language}-{difficulty}-{replicate + 1:03d}"
            records.append({
                "pack_id": case_id,
                "target": {
                    "case_id": case_id,
                    "primary_category": category,
                    "language": language,
                    "difficulty": difficulty,
                },
                "sources": [_source_payload(registry, source_id) for source_id in selected],
                "connection": connection,
                "generation_requirements": {
                    "natural_user_query": True,
                    "answer_points_are_conclusions_not_excerpts": True,
                    "chinese_query_and_gold_for_zh": language == "zh",
                    "comparison_requires_explicit_relationship": category == "comparison_multi_hop",
                    "second_turn_must_depend_on_first": category == "multi_turn_follow_up",
                    "tool_outputs_must_be_recomputed": category in {"size_test_calculation", "tool_chain"},
                    "negative_behavior_must_match_reason": category == "negative_insufficient",
                },
                "provenance_template": {
                    "generator_model": "gpt-5.6-terra-medium",
                    "generator_prompt_hash": PROMPT_HASH,
                    "source_snapshot_id": registry.manifest.snapshot_id,
                    "source_snapshot_hash": registry.manifest.source_sha256,
                    "random_seed": args.seed + ordinal,
                },
            })
            ordinal += 1
    write_jsonl(args.output, records)
    print(json.dumps({"packs": len(records), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
