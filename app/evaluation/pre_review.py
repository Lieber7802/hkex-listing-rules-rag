from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from app.evaluation.sampling import SamplingQuota, SamplingQuotaError
from app.evaluation.schemas import BenchmarkCase, CheckStatus, ValidationRecord


def static_checks_pass(record: ValidationRecord) -> bool:
    """Return whether every non-human gate has passed without treating review as approval."""
    return all(
        check.status in {CheckStatus.PASS, CheckStatus.NOT_APPLICABLE}
        for check in record.checks
        if check.check_name != "human_review"
    )


def select_pre_review_cases(
    cases: Iterable[BenchmarkCase],
    validation_records: Iterable[ValidationRecord],
    quota: SamplingQuota,
    seed: int,
) -> Tuple[List[BenchmarkCase], Dict[str, object]]:
    """Select a fixed-seed human-review set from statically valid candidates.

    This function deliberately never changes ``ValidationRecord.accepted``. Human
    approval remains a mandatory final gate handled by ``validate_benchmark.py``.
    """
    records = {record.case_id: record for record in validation_records}
    candidates = [
        case for case in cases
        if case.case_id in records
        and records[case.case_id].case_hash == case.content_hash()
        and static_checks_pass(records[case.case_id])
    ]
    by_cell: Dict[Tuple[str, str, str], List[BenchmarkCase]] = defaultdict(list)
    for case in candidates:
        by_cell[_joint_key(case)].append(case)

    deficits = {
        "|".join(cell.key): cell.count - len(by_cell.get(cell.key, []))
        for cell in quota.cells
        if len(by_cell.get(cell.key, [])) < cell.count
    }
    if deficits:
        raise SamplingQuotaError(deficits)

    selected: List[BenchmarkCase] = []
    for cell in sorted(quota.cells, key=lambda item: item.key):
        cell_cases = sorted(
            by_cell[cell.key],
            key=lambda case: (_stable_order_key(seed, case.case_id), case.case_id),
        )
        selected.extend(cell_cases[:cell.count])

    selected_ids = [case.case_id for case in selected]
    manifest = {
        "seed": seed,
        "target_size": quota.target_size,
        "static_eligible_pool_size": len(candidates),
        "selected_case_ids": selected_ids,
        "candidate_pool_hash": _pool_hash(candidates),
        "quota_hash": _json_hash([cell.model_dump(mode="json") for cell in quota.cells]),
        "joint_distribution": _distribution(selected, lambda case: "|".join(_joint_key(case))),
        "category_distribution": _distribution(selected, lambda case: case.primary_category.value),
        "language_distribution": _distribution(selected, lambda case: case.language.value),
        "difficulty_distribution": _distribution(selected, lambda case: case.difficulty.value),
        "review_state": "pending_human_approval",
    }
    return selected, manifest


def _joint_key(case: BenchmarkCase) -> Tuple[str, str, str]:
    return case.primary_category.value, case.language.value, case.difficulty.value


def _stable_order_key(seed: int, case_id: str) -> str:
    return hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pool_hash(cases: Sequence[BenchmarkCase]) -> str:
    payload = [
        {"case_id": case.case_id, "case_hash": case.content_hash()}
        for case in sorted(cases, key=lambda item: item.case_id)
    ]
    return _json_hash(payload)


def _distribution(cases: Iterable[BenchmarkCase], key) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for case in cases:
        counts[key(case)] += 1
    return dict(counts)
