import json
from datetime import date

import pytest

from app.evaluation.benchmark_generator import (
    _eligible_rule_sources,
    _graph_pairs,
    generate_candidate_files,
    generate_candidates,
)
from app.evaluation.sampling import QuotaCell, SamplingQuota
from app.evaluation.schemas import Difficulty, Language, PrimaryCategory, RouteMode
from app.evaluation.source_registry import SourceRegistry, build_source_registry


def _registry():
    records, manifest, _ = build_source_registry(
        [
            {
                "chunk_id": "main:14.34",
                "document_id": "main",
                "source_path": "data/raw/rules/main_board.pdf",
                "text": "14.34 Main Board Rule requires an announcement and disclosure for a notifiable transaction.",
                "rule_number": "14.34",
                "chapter": "14",
            },
            {
                "chunk_id": "main:14.52",
                "document_id": "main",
                "source_path": "data/raw/rules/main_board.pdf",
                "text": "14.52 Main Board Rule requires shareholder approval for a major transaction.",
                "rule_number": "14.52",
                "chapter": "14",
            },
        ],
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )
    return SourceRegistry(records, manifest=manifest)


def _quota():
    return SamplingQuota(cells=[
        QuotaCell(primary_category=PrimaryCategory.RULE_LOOKUP, language=Language.ENGLISH, difficulty=Difficulty.EASY, count=1),
        QuotaCell(primary_category=PrimaryCategory.COMPARISON_MULTI_HOP, language=Language.ENGLISH, difficulty=Difficulty.MEDIUM, count=1),
        QuotaCell(primary_category=PrimaryCategory.SIZE_TEST_CALCULATION, language=Language.CHINESE, difficulty=Difficulty.MEDIUM, count=1),
        QuotaCell(primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT, language=Language.ENGLISH, difficulty=Difficulty.HARD, count=1),
    ])


def _edges():
    return [{
        "src": "chunk:main:14.34",
        "dst": "chunk:main:14.52",
        "edge_type": "same_scenario",
        "weight": 0.7,
        "reason": "test",
        "evidence": [],
    }]


def test_generator_creates_typed_source_grounded_candidates():
    candidates = generate_candidates(_registry(), _edges(), _quota(), target_multiplier=1, seed=7)

    assert len(candidates) == 4
    assert len({case.case_id for case in candidates}) == 4
    assert all(case.provenance.generator_model == "codex-5.6-terra" for case in candidates)
    assert any(case.language == Language.CHINESE and "cross_lingual" in case.capability_tags for case in candidates)
    assert all(case.content_hash() for case in candidates)


def test_generator_accepts_a_release_specific_case_id_prefix():
    candidates = generate_candidates(
        _registry(), _edges(), _quota(), target_multiplier=1, seed=7,
        case_id_prefix="r2-v11",
    )

    assert all(case.case_id.startswith("r2-v11-") for case in candidates)


def test_generated_tool_cases_include_the_required_calculation_inputs_in_the_query():
    candidates = generate_candidates(_registry(), _edges(), _quota(), target_multiplier=1, seed=7)
    tool_case = next(case for case in candidates if case.primary_category == PrimaryCategory.SIZE_TEST_CALCULATION)

    query = tool_case.query.lower()
    assert "market cap" in query
    assert "total assets" in query
    assert "consideration" in query
    assert "acquisition" in query or "disposal" in query
    assert [call.tool_name for call in tool_case.expected_tool_calls] == ["size_test_calculator"]
    assert tool_case.expected_route == RouteMode.TOOL_ONLY
    assert tool_case.source_chunk_ids == []
    assert tool_case.expected_rules == []


def test_generated_tool_chain_uses_regulatory_evidence_in_addition_to_tool_outputs():
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.TOOL_CHAIN,
            language=Language.ENGLISH,
            difficulty=Difficulty.MEDIUM,
            count=1,
        ),
    ])
    tool_case = generate_candidates(_registry(), _edges(), quota, target_multiplier=1, seed=7)[0]

    assert [call.tool_name for call in tool_case.expected_tool_calls] == [
        "size_test_calculator",
        "transaction_classifier",
        "disclosure_checklist",
    ]
    assert tool_case.expected_route == RouteMode.TOOL_PLUS_RETRIEVAL
    assert len(tool_case.source_chunk_ids) == 1
    assert any(point.evidence_kind.value == "source" for point in tool_case.answer_points)
    assert any(point.evidence_kind.value == "tool" for point in tool_case.answer_points)


def test_generated_source_answer_points_are_atomic_claims_not_full_evidence_excerpts():
    candidates = generate_candidates(_registry(), _edges(), _quota(), target_multiplier=1, seed=7)
    source_points = [
        point
        for case in candidates
        for point in case.answer_points
        if point.evidence_kind.value == "source"
    ]

    assert source_points
    assert all(not point.text.startswith("Evidence excerpt from") for point in source_points)
    assert all(len(point.text) <= 360 for point in source_points)


def test_rule_lookup_candidates_expect_the_agentic_rule_lookup_route():
    candidates = generate_candidates(_registry(), _edges(), _quota(), target_multiplier=1, seed=7)
    rule_case = next(case for case in candidates if case.primary_category == PrimaryCategory.RULE_LOOKUP)

    assert rule_case.expected_route == RouteMode.TOOL_PLUS_RETRIEVAL


def test_generator_excludes_decision_paragraph_numbers_from_formal_rule_sources():
    records, manifest, _ = build_source_registry(
        [
            {
                "chunk_id": "main:14.34",
                "document_id": "main",
                "source_path": "data/raw/rules/main_board.pdf",
                "text": "14.34 Main Board Rule requires an announcement and disclosure for a notifiable transaction.",
                "rule_number": "14.34",
                "chapter": "14",
            },
            {
                "chunk_id": "decision:27",
                "document_id": "decision",
                "source_path": "data/raw/review_committee_decisions/decision.md",
                "text": "27. The company submitted that it had complied with GEM Rule 17.26 in the circumstances.",
                "rule_number": "27",
                "chapter": "decision",
            },
        ],
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )

    eligible = _eligible_rule_sources(SourceRegistry(records, manifest=manifest))

    assert [record.chunk_id for record in eligible] == ["main:14.34"]


def test_generator_excludes_near_duplicate_rule_pairs_from_comparison_cases():
    registry = _registry()
    records = {record.chunk_id: record for record in registry.records}
    duplicate = records["main:14.52"].model_copy(update={
        "chunk_id": "gem:19.52",
        "text": records["main:14.52"].text.replace("14.52", "19.52"),
    })
    records[duplicate.chunk_id] = duplicate

    with pytest.raises(ValueError, match="does not contain connected"):
        _graph_pairs([
            {
                "src": "chunk:main:14.52",
                "dst": "chunk:gem:19.52",
                "edge_type": "semantic_similarity",
            },
        ], records)


def test_generator_excludes_reference_release_multi_source_combinations():
    registry = _registry()
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.COMPARISON_MULTI_HOP,
            language=Language.ENGLISH,
            difficulty=Difficulty.MEDIUM,
            count=1,
        ),
    ])
    with pytest.raises(ValueError, match="no eligible source pairs remain"):
        generate_candidates(
            registry,
            _edges(),
            quota,
            target_multiplier=1,
            seed=7,
            excluded_multi_source_signatures={("main:14.34", "main:14.52")},
        )


def test_generator_writes_manifest_with_candidate_hash(tmp_path):
    registry = _registry()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    from app.evaluation.dataset_loader import write_json, write_jsonl

    write_jsonl(registry_dir / "sources.jsonl", registry.records)
    write_json(registry_dir / "snapshot_manifest.json", registry.manifest)
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    write_jsonl(graph_dir / "edges.jsonl", _edges())
    write_json(graph_dir / "graph_stats.json", {
        "nodes_sha256": "1" * 64,
        "edges_sha256": "2" * 64,
    })
    quota_path = tmp_path / "quota.json"
    quota_path.write_text(json.dumps(_quota().model_dump(mode="json")), encoding="utf-8")
    output = tmp_path / "candidates.jsonl"
    manifest_path = tmp_path / "manifest.json"

    manifest = generate_candidate_files(
        registry_dir / "sources.jsonl",
        graph_dir / "edges.jsonl",
        quota_path,
        output,
        manifest_path,
        target_multiplier=1,
        seed=9,
    )

    assert manifest.candidate_count == 4
    assert len(manifest.candidates_sha256) == 64
    assert output.exists()
    assert manifest_path.exists()


def test_generator_file_output_excludes_multi_source_pairs_from_reference_release(tmp_path):
    registry = _registry()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    from app.evaluation.dataset_loader import write_json, write_jsonl

    write_jsonl(registry_dir / "sources.jsonl", registry.records)
    write_json(registry_dir / "snapshot_manifest.json", registry.manifest)
    graph_dir = tmp_path / "graph"
    graph_dir.mkdir()
    write_jsonl(graph_dir / "edges.jsonl", _edges())
    write_json(graph_dir / "graph_stats.json", {
        "nodes_sha256": "1" * 64,
        "edges_sha256": "2" * 64,
    })
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        ),
    ])
    quota_path = tmp_path / "quota.json"
    quota_path.write_text(json.dumps(quota.model_dump(mode="json")), encoding="utf-8")
    reference = tmp_path / "reference.jsonl"
    write_jsonl(reference, [
        candidate for candidate in generate_candidates(_registry(), _edges(), _quota(), target_multiplier=1, seed=7)
        if candidate.primary_category == PrimaryCategory.COMPARISON_MULTI_HOP
    ])

    manifest = generate_candidate_files(
        registry_dir / "sources.jsonl",
        graph_dir / "edges.jsonl",
        quota_path,
        tmp_path / "candidates.jsonl",
        tmp_path / "manifest.json",
        target_multiplier=1,
        seed=7,
        reference_benchmark_path=reference,
    )

    assert manifest.excluded_reference_multi_source_count == 1
