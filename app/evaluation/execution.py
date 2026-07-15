from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.run_validation import validate_run_completeness
from app.evaluation.runners import AgenticRAGRunner, SYSTEM_CONFIGS, TraditionalHybridRAGRunner
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow, RunManifest
from app.core.config import settings
from app.retrieval.index_store import IndexStore


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file_path.relative_to(path).as_posix().encode())
        digest.update(sha256_file(file_path).encode())
    return digest.hexdigest()


def code_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def build_manifest(
    run_id: str, benchmark: Path, source_snapshot: Path, index_path: Path,
    config_id: str, release_manifest: Path | None = None,
) -> RunManifest:
    vector_dimension = None
    try:
        vector_dimension = IndexStore.load(index_path).vector_index.dimension
    except Exception:
        pass
    prompt_hash = hashlib.sha256(
        (Path("app/agents/planner_agent.py").read_text(encoding="utf-8") +
         Path("app/agents/reasoning_agent.py").read_text(encoding="utf-8")).encode("utf-8")
    ).hexdigest()
    release_payload = json.loads(release_manifest.read_text(encoding="utf-8")) if release_manifest else {}
    return RunManifest(
        run_id=run_id, benchmark_hash=sha256_file(benchmark),
        source_snapshot_hash=sha256_file(source_snapshot), index_hash=sha256_tree(index_path),
        model_id=settings.llm_model, provider=settings.llm_provider, prompt_hash=prompt_hash,
        generation_parameters={
            "system_id": config_id, "seed": 42, "planner_temperature": 0.0,
            "answer_temperature": 0.3,
            "max_tokens": 1000, "retrieval_top_k_bm25": settings.retrieval_top_k_bm25,
            "retrieval_top_k_dense": settings.retrieval_top_k_dense,
            "retrieval_top_k_final": settings.retrieval_top_k_final, "rrf_k": settings.rrf_k,
            "planner_mode": SYSTEM_CONFIGS[config_id].planner_mode,
            "enable_tools": SYSTEM_CONFIGS[config_id].enable_tools,
            "enable_coverage_retry": SYSTEM_CONFIGS[config_id].enable_coverage_retry,
            "max_retrieval_rounds": SYSTEM_CONFIGS[config_id].max_retrieval_rounds,
        }, code_revision=code_revision(),
        configuration_id=config_id, index_manifest_hash=sha256_tree(index_path),
        embedding_model=settings.embedding_model, embedding_dimension=vector_dimension,
        random_seed=42, release_version=release_payload.get("version"),
        release_manifest_hash=sha256_file(release_manifest) if release_manifest else None,
    )


def verify_release(benchmark: Path, source_snapshot: Path, release_manifest: Path) -> None:
    payload = json.loads(Path(release_manifest).read_text(encoding="utf-8"))
    files = payload.get("files", {})
    required = {"benchmark": benchmark, "source_snapshot": source_snapshot}
    for key, actual_path in required.items():
        record = files.get(key)
        if not record or sha256_file(actual_path) != record.get("sha256"):
            raise ValueError(f"release manifest does not validate {key}: {actual_path}")


def run_experiment(
    benchmark_path: Path, output_dir: Path, source_snapshot: Path, index_path: Path,
    systems: Sequence[str] = ("B3", "A1", "A2", "A3"), run_id: str | None = None,
    release_manifest: Path | None = None, timeout_seconds: float = 120.0,
    max_retries: int = 1,
) -> dict[str, Path]:
    if release_manifest is not None:
        verify_release(benchmark_path, source_snapshot, release_manifest)
    cases = read_jsonl(benchmark_path, BenchmarkCase)
    run_id = run_id or f"eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    output_dir = Path(output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    result_paths: dict[str, Path] = {}
    for system_id in systems:
        config = SYSTEM_CONFIGS[system_id]
        runner = TraditionalHybridRAGRunner(config) if system_id == "B3" else AgenticRAGRunner(config)
        result_path = output_dir / f"{system_id}_results.jsonl"
        rows: list[EvaluationRunRow] = read_jsonl(result_path, EvaluationRunRow) if result_path.exists() else []
        completed = {row.case_id for row in rows if row.row_type.value in {"single_turn", "aggregate"}}
        retries = 0
        for case in cases:
            if case.case_id in completed:
                continue
            attempts = 0
            while True:
                attempts += 1
                try:
                    executor = ThreadPoolExecutor(max_workers=1)
                    future = executor.submit(runner.run_case, case, run_id)
                    case_rows = future.result(timeout=timeout_seconds)
                    executor.shutdown(wait=True)
                    break
                except TimeoutError:
                    executor.shutdown(wait=False, cancel_futures=True)
                    case_rows = [_failure_row(run_id, system_id, case, f"timed out after {timeout_seconds}s")]
                except Exception as exc:
                    executor.shutdown(wait=False, cancel_futures=True)
                    case_rows = [_failure_row(run_id, system_id, case, str(exc))]
                if attempts > max_retries:
                    break
                retries += 1
            rows.extend(case_rows)
            write_jsonl(result_path, rows)
        issues = validate_run_completeness(rows, (case.case_id for case in cases), [system_id])
        if issues:
            raise ValueError(f"incomplete {system_id} run: {issues}")
        manifest = build_manifest(run_id, benchmark_path, source_snapshot, index_path, system_id, release_manifest)
        manifest.completed_at = datetime.now(timezone.utc)
        manifest.failure_count = sum(bool(row.error) for row in rows if row.row_type.value in {"single_turn", "aggregate"})
        manifest.retry_count = retries
        write_json(output_dir / f"{system_id}_manifest.json", manifest)
        result_paths[system_id] = result_path
    return result_paths


def _failure_row(run_id: str, system_id: str, case: BenchmarkCase, error: str) -> EvaluationRunRow:
    query = case.turns[-1].query if case.turns else case.query or ""
    return EvaluationRunRow(
        run_id=run_id, case_id=case.case_id, system=system_id,
        row_type="aggregate" if case.turns else "single_turn", query=query,
        answer="", latency_seconds=0.0, error=error,
    )
