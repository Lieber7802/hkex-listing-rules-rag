"""Build source packs for a small Terra-authored benchmark-generation pilot."""

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
from app.evaluation.source_registry import SourceRegistry, normalize_source_path


PROMPT = (
    "Author a natural, source-grounded HKEX BenchmarkCase. Gold answer points must be concise "
    "conclusions that answer the query, not source excerpts. Preserve exact evidence and ruleset identity."
)
PROMPT_HASH = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()
PRECISE_RULE = re.compile(r"^\d{1,2}[A-Z]?(?:\.\d+[A-Z]?)$", re.IGNORECASE)


TARGETS = (
    ("rule_lookup", "en", "easy"),
    ("rule_lookup", "zh", "easy"),
    ("obligation_summary", "en", "medium"),
    ("obligation_summary", "zh", "medium"),
    ("procedure_flow", "en", "medium"),
    ("procedure_flow", "zh", "medium"),
    ("comparison_multi_hop", "en", "hard"),
    ("comparison_multi_hop", "zh", "hard"),
    ("size_test_calculation", "en", "medium"),
    ("size_test_calculation", "zh", "medium"),
    ("tool_chain", "en", "hard"),
    ("tool_chain", "zh", "hard"),
    ("multi_turn_follow_up", "en", "hard"),
    ("multi_turn_follow_up", "zh", "hard"),
    ("negative_insufficient", "en", "medium"),
    ("negative_insufficient", "zh", "medium"),
)


def main() -> None:
    registry_path = Path("data/evaluation/source_registry/sources.jsonl")
    nodes_path = Path("data/evaluation/source_graph/nodes.jsonl")
    edges_path = Path("data/evaluation/source_graph/edges.jsonl")
    output_path = Path("data/evaluation/pilot/generation_packs.jsonl")
    registry = SourceRegistry.load(registry_path)
    nodes = {row["chunk_id"]: row for row in read_jsonl(nodes_path)}
    source_ids = {
        record.chunk_id
        for record in registry.records
        if record.eligible_main_benchmark
        and "/rules/" in normalize_source_path(record.source_path)
        and record.ruleset.value in {"main_board", "gem"}
        and record.rule_number
        and PRECISE_RULE.fullmatch(record.rule_number.strip())
    }
    scenario_sources = defaultdict(list)
    for source_id in source_ids:
        for scenario in nodes[source_id]["scenarios"]:
            scenario_sources[scenario].append(source_id)
    for values in scenario_sources.values():
        values.sort()
    all_sources = sorted(source_ids)
    connected_pairs = []
    for edge in read_jsonl(edges_path):
        if edge["edge_type"] not in {"rule_reference", "same_scenario", "semantic_similarity"}:
            continue
        left = edge["src"].removeprefix("chunk:")
        right = edge["dst"].removeprefix("chunk:")
        if left in source_ids and right in source_ids and registry.require(left).rule_number != registry.require(right).rule_number:
            connected_pairs.append((left, right, edge))
    connected_pairs.sort(key=lambda item: (item[0], item[1], item[2]["edge_type"]))
    if len(connected_pairs) < 20:
        raise RuntimeError("not enough precise connected rule pairs for generation pilot")

    records = []
    for target_index, (category, language, difficulty) in enumerate(TARGETS):
        for replicate in range(2):
            ordinal = target_index * 2 + replicate
            if category in {"comparison_multi_hop", "multi_turn_follow_up"}:
                left, right, edge = connected_pairs[(ordinal * 97) % len(connected_pairs)]
                selected = [left, right]
                connection = edge
            else:
                scenario = {
                    "obligation_summary": "disclosure_obligation",
                    "procedure_flow": "procedure_flow",
                    "size_test_calculation": "size_test",
                    "tool_chain": "notifiable_transaction",
                }.get(category)
                pool = scenario_sources.get(scenario, all_sources) if scenario else all_sources
                selected = [pool[(ordinal * 101) % len(pool)]]
                connection = None
            sources = []
            for source_id in selected:
                source = registry.require(source_id)
                sources.append({
                    "chunk_id": source.chunk_id,
                    "ruleset": source.ruleset.value,
                    "rule_number": source.rule_number,
                    "chapter": source.chapter,
                    "section_title": source.section_title,
                    "source_path": source.source_path,
                    "text": source.text,
                })
            records.append({
                "pack_id": f"pilot-{category}-{language}-{replicate + 1:02d}",
                "target": {
                    "case_id": f"pilot-{category}-{language}-{replicate + 1:02d}",
                    "primary_category": category,
                    "language": language,
                    "difficulty": difficulty,
                },
                "sources": sources,
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
                    "random_seed": 42 + ordinal,
                },
            })
    write_jsonl(output_path, records)
    print(json.dumps({"packs": len(records), "output": str(output_path)}, indent=2))


if __name__ == "__main__":
    main()
