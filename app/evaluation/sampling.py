from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from pydantic import Field, model_validator

from app.evaluation.schemas import (
    BenchmarkCase,
    Difficulty,
    Language,
    PrimaryCategory,
    StrictModel,
    ValidationRecord,
)


class QuotaCell(StrictModel):
    primary_category: PrimaryCategory
    language: Language
    difficulty: Difficulty
    count: int = Field(ge=0)

    @property
    def key(self) -> Tuple[str, str, str]:
        return (
            self.primary_category.value,
            self.language.value,
            self.difficulty.value,
        )


class SamplingQuota(StrictModel):
    cells: List[QuotaCell]

    @model_validator(mode="after")
    def validate_cells(self) -> "SamplingQuota":
        keys = [cell.key for cell in self.cells]
        if len(keys) != len(set(keys)):
            raise ValueError("sampling quota contains duplicate joint cells")
        if not self.cells or sum(cell.count for cell in self.cells) <= 0:
            raise ValueError("sampling quota must request at least one case")
        return self

    @property
    def target_size(self) -> int:
        return sum(cell.count for cell in self.cells)

    def category_totals(self) -> Dict[str, int]:
        return _marginal_totals(self.cells, 0)

    def language_totals(self) -> Dict[str, int]:
        return _marginal_totals(self.cells, 1)

    def difficulty_totals(self) -> Dict[str, int]:
        return _marginal_totals(self.cells, 2)


class SamplingManifest(StrictModel):
    seed: int
    pool_hash: str
    quota_hash: str
    target_size: int
    accepted_pool_size: int
    selected_case_ids: List[str]
    unselected_accepted_case_ids: List[str]
    joint_distribution: Dict[str, int]
    category_distribution: Dict[str, int]
    language_distribution: Dict[str, int]
    difficulty_distribution: Dict[str, int]


class SamplingQuotaError(ValueError):
    def __init__(self, deficits: Mapping[str, int]):
        self.deficits = dict(deficits)
        detail = ", ".join(f"{key}: missing {value}" for key, value in sorted(deficits.items()))
        super().__init__(f"accepted pool cannot satisfy sampling quota ({detail})")


def _marginal_totals(cells: Sequence[QuotaCell], index: int) -> Dict[str, int]:
    totals: Dict[str, int] = defaultdict(int)
    for cell in cells:
        totals[cell.key[index]] += cell.count
    return dict(totals)


def _stable_order_key(seed: int, case_id: str) -> str:
    return hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()


def _joint_key(case: BenchmarkCase) -> Tuple[str, str, str]:
    return (
        case.primary_category.value,
        case.language.value,
        case.difficulty.value,
    )


def _serialized_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StratifiedSampler:
    def select(
        self,
        cases: Iterable[BenchmarkCase],
        validation_records: Iterable[ValidationRecord],
        quota: SamplingQuota,
        seed: int,
    ) -> Tuple[List[BenchmarkCase], SamplingManifest]:
        case_list = list(cases)
        validation_list = [
            ValidationRecord.model_validate(record.model_dump())
            for record in validation_records
        ]
        validation_case_ids = [record.case_id for record in validation_list]
        duplicate_validation_ids = sorted({
            case_id
            for case_id in validation_case_ids
            if validation_case_ids.count(case_id) > 1
        })
        if duplicate_validation_ids:
            raise ValueError(
                f"duplicate validation record case_id values: {duplicate_validation_ids}"
            )
        validations = {record.case_id: record for record in validation_list}
        accepted_cases: List[BenchmarkCase] = []
        seen_case_ids: set[str] = set()

        for case in case_list:
            if case.case_id in seen_case_ids:
                raise ValueError(f"duplicate benchmark case_id: {case.case_id}")
            seen_case_ids.add(case.case_id)
            record = validations.get(case.case_id)
            if record and record.accepted:
                if record.case_hash != case.content_hash():
                    raise ValueError(
                        f"validation record hash does not match benchmark case: {case.case_id}"
                    )
                accepted_cases.append(case)

        by_cell: Dict[Tuple[str, str, str], List[BenchmarkCase]] = defaultdict(list)
        for case in accepted_cases:
            by_cell[_joint_key(case)].append(case)

        deficits: Dict[str, int] = {}
        for cell in quota.cells:
            available = len(by_cell.get(cell.key, []))
            if available < cell.count:
                deficits["|".join(cell.key)] = cell.count - available
        if deficits:
            raise SamplingQuotaError(deficits)

        selected: List[BenchmarkCase] = []
        for cell in sorted(quota.cells, key=lambda item: item.key):
            candidates = sorted(
                by_cell.get(cell.key, []),
                key=lambda case: (_stable_order_key(seed, case.case_id), case.case_id),
            )
            selected.extend(candidates[:cell.count])

        selected_ids = [case.case_id for case in selected]
        selected_id_set = set(selected_ids)
        unselected = sorted(
            case.case_id for case in accepted_cases if case.case_id not in selected_id_set
        )

        joint_distribution: Dict[str, int] = defaultdict(int)
        category_distribution: Dict[str, int] = defaultdict(int)
        language_distribution: Dict[str, int] = defaultdict(int)
        difficulty_distribution: Dict[str, int] = defaultdict(int)
        for case in selected:
            joint_distribution["|".join(_joint_key(case))] += 1
            category_distribution[case.primary_category.value] += 1
            language_distribution[case.language.value] += 1
            difficulty_distribution[case.difficulty.value] += 1

        pool_payload = [
            {
                "case_id": case.case_id,
                "cell": _joint_key(case),
                "validation_policy": validations[case.case_id].acceptance_policy_version,
            }
            for case in sorted(accepted_cases, key=lambda item: item.case_id)
        ]
        quota_payload = [cell.model_dump(mode="json") for cell in sorted(quota.cells, key=lambda item: item.key)]
        manifest = SamplingManifest(
            seed=seed,
            pool_hash=_serialized_hash(pool_payload),
            quota_hash=_serialized_hash(quota_payload),
            target_size=quota.target_size,
            accepted_pool_size=len(accepted_cases),
            selected_case_ids=selected_ids,
            unselected_accepted_case_ids=unselected,
            joint_distribution=dict(joint_distribution),
            category_distribution=dict(category_distribution),
            language_distribution=dict(language_distribution),
            difficulty_distribution=dict(difficulty_distribution),
        )
        return selected, manifest
