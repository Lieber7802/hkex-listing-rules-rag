import json
import pickle
from datetime import date

import numpy as np

from app.evaluation.source_graph import (
    build_source_graph,
    build_source_graph_files,
    extract_rule_references,
    infer_language,
)
from app.evaluation.source_registry import SourceRegistry, build_source_registry
from app.evaluation.schemas import Language, RuleSet


def _registry(chunks):
    records, manifest, _ = build_source_registry(
        chunks,
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )
    return SourceRegistry(records, manifest=manifest)


def _chunk(chunk_id, source_path, text, rule_number=None, chapter=None, section_title=None):
    return {
        "chunk_id": chunk_id,
        "document_id": chunk_id.split(":")[0],
        "source_path": source_path,
        "text": text,
        "rule_number": rule_number,
        "chapter": chapter,
        "section_title": section_title,
    }


def test_graph_contains_only_eligible_canonical_nodes_and_structural_edges():
    registry = _registry([
        _chunk(
            "main:14.34:a",
            "data/raw/rules/main_board.pdf",
            "Main Board Rule 14.34 requires an announcement for a notifiable transaction.",
            "14.34",
            "14",
            "Notification and announcement",
        ),
        _chunk(
            "main:14.34:b",
            "data/raw/rules/main_board.pdf",
            "Rule 14.34 also describes announcement content and disclosure obligations.",
            "14.34",
            "14",
            "Notification and announcement",
        ),
        _chunk(
            "archive:old",
            "data/raw/archive/guidance_letters/old.pdf",
            "Archived guidance about a connected transaction and announcement requirements.",
            "14A.35",
            "14A",
        ),
    ])

    nodes, edges, stats = build_source_graph(registry)

    assert {node.chunk_id for node in nodes} == {"main:14.34:a", "main:14.34:b"}
    assert all(node.eligible_main_benchmark and node.duplicate_of is None for node in nodes)
    assert any(edge.edge_type == "same_rule" for edge in edges)
    assert stats.node_count == 2
    assert stats.edge_count == len(edges)
    assert stats.semantic_edges_enabled is False


def test_rule_reference_extraction_preserves_board_identity():
    references = extract_rule_references(
        "Main Board Rule 14A.35 and GEM Rule 19.06 apply in different rulebooks.",
        RuleSet.GUIDANCE,
    )

    assert references == [
        (RuleSet.GEM, "19.06"),
        (RuleSet.MAIN_BOARD, "14A.35"),
    ]


def test_language_detection_preserves_material_mixed_language_text():
    assert infer_language("Rule 14.34 requires disclosure. 發行人必須刊發公告。") == Language.MIXED
    assert infer_language("Rule 14.34 requires disclosure.") == Language.ENGLISH
    assert infer_language("Company Law (公司法) applies to this issuer.") == Language.ENGLISH
    assert infer_language("發行人必須遵守上市規則並刊發公告。") == Language.CHINESE


def test_semantic_edges_reuse_existing_faiss_vectors(tmp_path):
    import faiss

    chunks = [
        _chunk(
            "main:a",
            "data/raw/rules/main_board.pdf",
            "A sufficiently long rule passage about notification requirements.",
        ),
        _chunk(
            "main:b",
            "data/raw/rules/main_board.pdf",
            "A different sufficiently long rule passage about issuer obligations.",
        ),
    ]
    registry = _registry(chunks)
    vectors = np.asarray([[1.0, 0.0], [0.99, 0.01]], dtype=np.float32)
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(2)
    index.add(vectors)
    index_path = tmp_path / "faiss_index.bin"
    ids_path = tmp_path / "chunk_ids.pkl"
    faiss.write_index(index, str(index_path))
    with ids_path.open("wb") as handle:
        pickle.dump(["main:a", "main:b"], handle)

    _, edges, stats = build_source_graph(
        registry,
        vector_index_path=index_path,
        chunk_ids_path=ids_path,
        semantic_top_k=1,
        semantic_threshold=0.9,
        max_semantic_edges_per_node=1,
    )

    assert any(edge.edge_type == "semantic_similarity" for edge in edges)
    assert stats.semantic_edges_enabled is True


def test_graph_files_round_trip(tmp_path):
    registry = _registry([
        _chunk(
            "main:a",
            "data/raw/rules/main_board.pdf",
            "Rule 14.34 contains enough text for a graph node and disclosure scenario.",
            "14.34",
            "14",
        )
    ])
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    from app.evaluation.dataset_loader import write_json, write_jsonl

    write_jsonl(registry_dir / "sources.jsonl", registry.records)
    write_json(registry_dir / "snapshot_manifest.json", registry.manifest)

    output_dir = tmp_path / "graph"
    stats = build_source_graph_files(registry_dir / "sources.jsonl", output_dir)

    assert stats.node_count == 1
    assert json.loads((output_dir / "graph_stats.json").read_text(encoding="utf-8"))["node_count"] == 1
    assert (output_dir / "nodes.jsonl").exists()
    assert (output_dir / "edges.jsonl").exists()
    assert len(stats.nodes_sha256) == 64
    assert len(stats.edges_sha256) == 64
