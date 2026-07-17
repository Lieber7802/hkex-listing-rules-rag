import json
import subprocess
import sys
from pathlib import Path

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.sampling import QuotaCell, SamplingQuota
from app.evaluation.schemas import (
    BenchmarkCase,
    Difficulty,
    Language,
    PrimaryCategory,
    ValidationRecord,
)
from tests.evaluation_helpers import answerable_case, approved_review, passing_judge


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    return subprocess.run(
        [sys.executable, *map(str, args)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_snapshot_validate_and_sample_cli_round_trip(tmp_path):
    chunks = tmp_path / "chunks.json"
    chunks.write_text(
        json.dumps([
            {
                "chunk_id": "chunk-main",
                "document_id": "main",
                "source_path": "data/raw/rules/main_board.pdf",
                "rule_number": "14.34",
                "chapter": "14",
                "section_title": "Notification and announcement",
                "text": (
                    "Main Board Rule 14.34 requires an issuer to publish an announcement "
                    "for a notifiable transaction and include the required details."
                ),
            }
        ]),
        encoding="utf-8",
    )
    registry_dir = tmp_path / "registry"
    build = _run(
        "scripts/build_evaluation_snapshot.py",
        "--chunks",
        chunks,
        "--output-dir",
        registry_dir,
        "--snapshot-date",
        "2026-07-11",
        "--min-text-chars",
        "20",
    )
    assert build.returncode == 0, build.stderr

    manifest = json.loads((registry_dir / "snapshot_manifest.json").read_text(encoding="utf-8"))
    case = answerable_case()
    case = case.model_copy(update={
        "provenance": case.provenance.model_copy(update={
            "source_snapshot_id": manifest["snapshot_id"],
            "source_snapshot_hash": manifest["source_sha256"],
        })
    })
    candidates = tmp_path / "candidates.jsonl"
    judges = tmp_path / "judges.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    validations = tmp_path / "validations.jsonl"
    accepted_pool = tmp_path / "accepted.jsonl"
    write_jsonl(candidates, [case])
    write_jsonl(judges, [{
        "case_id": case.case_id,
        "assessment": passing_judge(case).model_dump(mode="json"),
    }])
    write_jsonl(reviews, [{
        "case_id": case.case_id,
        "review": approved_review(case).model_dump(mode="json"),
    }])

    validate = _run(
        "scripts/validate_benchmark.py",
        "--candidates",
        candidates,
        "--source-registry",
        registry_dir / "sources.jsonl",
        "--judge-assessments",
        judges,
        "--human-reviews",
        reviews,
        "--validation-output",
        validations,
        "--accepted-output",
        accepted_pool,
        "--require-accepted",
        "1",
    )
    assert validate.returncode == 0, validate.stderr
    assert read_jsonl(accepted_pool, BenchmarkCase)[0].case_id == case.case_id
    assert read_jsonl(validations, ValidationRecord)[0].accepted is True

    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])
    quota_path = tmp_path / "quota.json"
    quota_path.write_text(quota.model_dump_json(indent=2), encoding="utf-8")
    benchmark_output = tmp_path / "benchmark.jsonl"
    sampling_manifest = tmp_path / "sampling.json"
    sample = _run(
        "scripts/sample_benchmark.py",
        "--accepted-pool",
        accepted_pool,
        "--validation-records",
        validations,
        "--quota",
        quota_path,
        "--seed",
        "42",
        "--output",
        benchmark_output,
        "--manifest-output",
        sampling_manifest,
    )
    assert sample.returncode == 0, sample.stderr
    assert read_jsonl(benchmark_output, BenchmarkCase)[0].case_id == case.case_id
    assert json.loads(sampling_manifest.read_text(encoding="utf-8"))["seed"] == 42
