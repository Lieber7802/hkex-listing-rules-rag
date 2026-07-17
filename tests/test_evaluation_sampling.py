import json
from pathlib import Path

import pytest

from app.evaluation.sampling import (
    QuotaCell,
    SamplingQuota,
    SamplingQuotaError,
    StratifiedSampler,
)
from app.evaluation.schemas import Difficulty, Language, PrimaryCategory, ReviewStatus
from tests.evaluation_helpers import accepted_validation, answerable_case


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_300_case_quota_matches_all_declared_margins():
    quota_path = PROJECT_ROOT / "app/evaluation/default_benchmark_quota.json"
    quota = SamplingQuota.model_validate(json.loads(quota_path.read_text(encoding="utf-8")))

    assert quota.target_size == 300
    assert quota.category_totals() == {
        "rule_lookup": 50,
        "obligation_summary": 50,
        "procedure_flow": 40,
        "comparison_multi_hop": 45,
        "size_test_calculation": 40,
        "tool_chain": 30,
        "multi_turn_follow_up": 25,
        "negative_insufficient": 20,
    }
    assert quota.language_totals() == {"en": 210, "zh": 90}
    assert quota.difficulty_totals() == {"easy": 105, "medium": 135, "hard": 60}


def _case(case_id, category, language, difficulty):
    query = (
        f"规则查询 {case_id}"
        if language == Language.CHINESE
        else f"Rule lookup question {case_id}"
    )
    return answerable_case(
        case_id=case_id,
        query=query,
        language=language,
        category=category,
        difficulty=difficulty,
    )


def test_joint_quota_sampling_is_exact_and_reproducible():
    cases = [
        _case("en-easy-1", PrimaryCategory.RULE_LOOKUP, Language.ENGLISH, Difficulty.EASY),
        _case("en-easy-2", PrimaryCategory.RULE_LOOKUP, Language.ENGLISH, Difficulty.EASY),
        _case("zh-hard-1", PrimaryCategory.RULE_LOOKUP, Language.CHINESE, Difficulty.HARD),
        _case("zh-hard-2", PrimaryCategory.RULE_LOOKUP, Language.CHINESE, Difficulty.HARD),
    ]
    records = [accepted_validation(case) for case in cases]
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        ),
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.CHINESE,
            difficulty=Difficulty.HARD,
            count=1,
        ),
    ])

    selected_one, manifest_one = StratifiedSampler().select(cases, records, quota, seed=42)
    selected_two, manifest_two = StratifiedSampler().select(cases, records, quota, seed=42)

    assert [case.case_id for case in selected_one] == [case.case_id for case in selected_two]
    assert manifest_one == manifest_two
    assert manifest_one.target_size == 2
    assert manifest_one.language_distribution == {"en": 1, "zh": 1}
    assert manifest_one.difficulty_distribution == {"easy": 1, "hard": 1}


def test_sampler_fails_with_explicit_joint_cell_deficit():
    case = _case(
        "en-easy",
        PrimaryCategory.RULE_LOOKUP,
        Language.ENGLISH,
        Difficulty.EASY,
    )
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.CHINESE,
            difficulty=Difficulty.HARD,
            count=1,
        )
    ])

    with pytest.raises(SamplingQuotaError) as exc_info:
        StratifiedSampler().select(
            [case],
            [accepted_validation(case)],
            quota,
            seed=42,
        )

    assert exc_info.value.deficits == {"rule_lookup|zh|hard": 1}


def test_sampler_rejects_tampered_case_after_validation():
    original = _case(
        "case-1",
        PrimaryCategory.RULE_LOOKUP,
        Language.ENGLISH,
        Difficulty.EASY,
    )
    tampered = original.model_copy(update={"query": "A modified query after validation"})
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])

    with pytest.raises(ValueError, match="hash does not match"):
        StratifiedSampler().select(
            [tampered],
            [accepted_validation(original)],
            quota,
            seed=1,
        )


def test_sampler_recomputes_stale_acceptance_before_selection():
    case = _case(
        "case-1",
        PrimaryCategory.RULE_LOOKUP,
        Language.ENGLISH,
        Difficulty.EASY,
    )
    record = accepted_validation(case)
    record.human_reviews[0].status = ReviewStatus.PENDING
    assert record.accepted is True
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])

    with pytest.raises(SamplingQuotaError):
        StratifiedSampler().select([case], [record], quota, seed=1)


def test_sampler_rejects_duplicate_validation_records():
    case = _case(
        "case-1",
        PrimaryCategory.RULE_LOOKUP,
        Language.ENGLISH,
        Difficulty.EASY,
    )
    record = accepted_validation(case)
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])

    with pytest.raises(ValueError, match="duplicate validation record"):
        StratifiedSampler().select([case], [record, record], quota, seed=1)
