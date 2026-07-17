import json
from datetime import date

from app.evaluation.source_registry import (
    SourceRegistry,
    build_source_registry,
    build_source_registry_file,
    infer_ruleset,
    infer_source_status,
)
from app.evaluation.schemas import RuleSet, SourceStatus


def _chunk(chunk_id: str, source_path: str, text: str, rule_number=None):
    return {
        "chunk_id": chunk_id,
        "document_id": chunk_id.split(":")[0],
        "source_path": source_path,
        "text": text,
        "rule_number": rule_number,
    }


def test_source_status_is_fail_closed_and_withdrawn_has_precedence():
    assert infer_source_status("data/raw/unknown/file.pdf", "current text") == SourceStatus.UNKNOWN
    assert infer_source_status("data/raw/archive/file.pdf", "current text") == SourceStatus.ARCHIVED
    assert (
        infer_source_status("data/raw/rules/main_board.pdf", "Withdrawn on 1 January")
        == SourceStatus.WITHDRAWN
    )
    assert (
        infer_source_status(
            "data/raw/rules/main_board.pdf",
            "An application may be withdrawn by the applicant before listing.",
        )
        == SourceStatus.ACTIVE
    )


def test_document_status_is_propagated_to_all_chunks():
    chunks = [
        _chunk(
            "doc:1",
            "data/raw/guidance/current.pdf",
            "Withdrawn on 1 January 2025 because the guidance was superseded.",
        ),
        _chunk(
            "doc:2",
            "data/raw/guidance/current.pdf",
            "This second chunk does not repeat the withdrawal notice but belongs to the same file.",
        ),
    ]
    records, _, _ = build_source_registry(
        chunks,
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )

    assert {record.status for record in records} == {SourceStatus.WITHDRAWN}
    assert all(record.eligible_main_benchmark is False for record in records)


def test_ruleset_identity_is_preserved():
    assert infer_ruleset("data/raw/rules/main_board.pdf") == RuleSet.MAIN_BOARD
    assert infer_ruleset("data/raw/rules/gem.pdf") == RuleSet.GEM
    assert infer_ruleset("data/raw/guidance/current.pdf") == RuleSet.GUIDANCE


def test_registry_excludes_archive_unknown_and_exact_duplicates():
    text = "Rule 14.34 requires an issuer to publish an announcement for this transaction."
    chunks = [
        _chunk("archive:1", "data/raw/archive/guidance_letters/old.pdf", text, "14.34"),
        _chunk("active:1", "data/raw/rules/main_board.pdf", text, "14.34"),
        _chunk("unknown:1", "data/raw/misc/file.pdf", "A sufficiently long but unclassified source passage for testing."),
    ]
    records, manifest, duplicate_map = build_source_registry(
        chunks,
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )
    registry = SourceRegistry(records)

    assert registry.require("active:1").eligible_main_benchmark is True
    assert registry.require("archive:1").eligible_main_benchmark is False
    assert registry.require("archive:1").duplicate_of == "active:1"
    assert registry.require("unknown:1").eligible_main_benchmark is False
    assert manifest.duplicate_groups == 1
    assert manifest.chunks_in_duplicate_groups == 2
    assert duplicate_map == [
        {
            "chunk_id": "archive:1",
            "canonical_chunk_id": "active:1",
            "canonical_text_hash": registry.require("active:1").canonical_text_hash,
        }
    ]


def test_effective_dates_are_enforced():
    chunk = _chunk(
        "future:1",
        "data/raw/rules/main_board.pdf",
        "A current-looking rule passage that is not yet effective on the snapshot date.",
    )
    records, _, _ = build_source_registry(
        [chunk],
        snapshot_date=date(2026, 7, 11),
        metadata_overrides={"future:1": {"effective_from": "2026-08-01"}},
        min_text_chars=20,
    )
    assert records[0].eligible_main_benchmark is False
    assert "not_yet_effective" in records[0].exclusion_reasons


def test_snapshot_files_round_trip(tmp_path):
    chunks_path = tmp_path / "chunks.json"
    chunks_path.write_text(
        json.dumps([
            _chunk(
                "main:1",
                "data/raw/rules/main_board.pdf",
                "Rule 14.34 contains enough text to be eligible for the benchmark source registry.",
                "14.34",
            )
        ]),
        encoding="utf-8",
    )
    output = tmp_path / "registry"
    manifest = build_source_registry_file(
        chunks_path,
        output,
        snapshot_date=date(2026, 7, 11),
        min_text_chars=20,
    )
    loaded = SourceRegistry.load(output / "sources.jsonl")

    assert manifest.total_chunks == 1
    assert loaded.require("main:1").eligible_main_benchmark is True
    assert (output / "duplicate_map.jsonl").exists()
    assert (output / "snapshot_manifest.json").exists()
