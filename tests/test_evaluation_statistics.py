import pytest

from app.evaluation.schemas import HumanReview, ReviewStatus
from app.evaluation.statistics import (
    human_review_agreement,
    mcnemar_exact,
    paired_bootstrap_difference,
    paired_clustered_pooled_bootstrap_difference,
)


def test_paired_bootstrap_is_reproducible_and_uses_paired_difference():
    baseline = {"a": 0.2, "b": 0.4, "c": 0.6}
    agentic = {"a": 0.4, "b": 0.5, "c": 0.9}

    first = paired_bootstrap_difference(
        baseline,
        agentic,
        bootstrap_samples=500,
        seed=7,
    )
    second = paired_bootstrap_difference(
        baseline,
        agentic,
        bootstrap_samples=500,
        seed=7,
    )

    assert first == second
    assert first.mean_difference == pytest.approx(0.2)
    assert first.ci_low <= first.mean_difference <= first.ci_high


def test_paired_bootstrap_rejects_unpaired_case_ids():
    with pytest.raises(ValueError, match="identical case IDs"):
        paired_bootstrap_difference(
            {"a": 1.0},
            {"b": 1.0},
            bootstrap_samples=100,
        )


def test_clustered_pooled_bootstrap_uses_point_totals_while_resampling_whole_cases():
    baseline = {
        "one-point": [True],
        "four-point": [False, False, False, False],
    }
    agentic = {
        "one-point": [False],
        "four-point": [True, True, True, True],
    }

    result = paired_clustered_pooled_bootstrap_difference(
        baseline,
        agentic,
        bootstrap_samples=500,
        seed=7,
    )

    assert result.case_count == 2
    assert result.mean_difference == pytest.approx(0.6)
    assert result.ci_low <= result.mean_difference <= result.ci_high


def test_mcnemar_exact_counts_discordant_pairs():
    baseline = {"a": True, "b": False, "c": False, "d": True}
    agentic = {"a": False, "b": True, "c": True, "d": True}

    result = mcnemar_exact(baseline, agentic)

    assert result.discordant_a_only == 1
    assert result.discordant_b_only == 2
    assert 0.0 <= result.exact_two_sided_p_value <= 1.0


def test_human_review_agreement_reports_second_review_rate_and_evidence_overlap():
    primary = HumanReview(
        case_hash="1" * 64,
        reviewer_id="reviewer-1",
        status=ReviewStatus.APPROVED,
        dimension_decisions={"source_support": True, "rule_references": True},
        verified_chunk_ids=["chunk-a", "chunk-b"],
    )
    secondary = HumanReview(
        case_hash="1" * 64,
        reviewer_id="reviewer-2",
        status=ReviewStatus.APPROVED,
        second_review=True,
        dimension_decisions={"source_support": True, "rule_references": False},
        verified_chunk_ids=["chunk-a", "chunk-c"],
    )
    single = HumanReview(
        case_hash="2" * 64,
        reviewer_id="reviewer-1",
        status=ReviewStatus.APPROVED,
    )

    result = human_review_agreement({
        "case-1": [primary, secondary],
        "case-2": [single],
    })

    assert result.second_review_case_count == 1
    assert result.second_review_rate == pytest.approx(0.5)
    assert result.status_exact_agreement == 1.0
    assert result.dimension_comparison_count == 2
    assert result.dimension_exact_agreement == pytest.approx(0.5)
    assert result.evidence_mapping_exact_agreement == 0.0
    assert result.evidence_mapping_mean_jaccard == pytest.approx(1 / 3)
