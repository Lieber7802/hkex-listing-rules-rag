from __future__ import annotations

import math
import random
from collections import Counter
from typing import Dict, List, Mapping, Optional, Sequence

from pydantic import Field

from app.evaluation.schemas import HumanReview, StrictModel


class PairedDifferenceSummary(StrictModel):
    case_count: int = Field(ge=1)
    mean_difference: float
    ci_low: float
    ci_high: float
    confidence_level: float = Field(gt=0.0, lt=1.0)
    bootstrap_samples: int = Field(ge=100)
    seed: int


class McNemarResult(StrictModel):
    discordant_a_only: int = Field(ge=0)
    discordant_b_only: int = Field(ge=0)
    exact_two_sided_p_value: float = Field(ge=0.0, le=1.0)


class HumanReviewAgreement(StrictModel):
    total_case_count: int = Field(ge=1)
    second_review_case_count: int = Field(ge=1)
    second_review_rate: float = Field(ge=0.0, le=1.0)
    status_exact_agreement: float = Field(ge=0.0, le=1.0)
    status_cohen_kappa: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    dimension_comparison_count: int = Field(ge=0)
    dimension_exact_agreement: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_mapping_case_count: int = Field(ge=0)
    evidence_mapping_exact_agreement: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    evidence_mapping_mean_jaccard: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    excluded_case_ids: List[str] = Field(default_factory=list)


def _cohen_kappa(left: Sequence[str], right: Sequence[str]) -> Optional[float]:
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right))
        for label in set(left_counts) | set(right_counts)
    )
    if math.isclose(expected, 1.0):
        return None
    return (observed - expected) / (1.0 - expected)


def human_review_agreement(
    reviews_by_case: Mapping[str, Sequence[HumanReview]],
) -> HumanReviewAgreement:
    if not reviews_by_case:
        raise ValueError("human review agreement requires at least one reviewed case")

    pairs = []
    excluded_case_ids: List[str] = []
    for case_id, reviews in sorted(reviews_by_case.items()):
        non_adjudicators = [review for review in reviews if not review.adjudicates_reviewers]
        primary = [review for review in non_adjudicators if not review.second_review]
        secondary = [review for review in non_adjudicators if review.second_review]
        if not secondary:
            continue
        if len(primary) != 1 or len(secondary) != 1:
            excluded_case_ids.append(case_id)
            continue
        if primary[0].reviewer_id == secondary[0].reviewer_id:
            excluded_case_ids.append(case_id)
            continue
        pairs.append((primary[0], secondary[0]))

    if not pairs:
        raise ValueError("no valid primary/second-review pairs are available")

    left_statuses = [left.status.value for left, _ in pairs]
    right_statuses = [right.status.value for _, right in pairs]
    dimension_matches: List[bool] = []
    evidence_exact: List[bool] = []
    evidence_jaccard: List[float] = []
    for left, right in pairs:
        shared_dimensions = set(left.dimension_decisions) & set(right.dimension_decisions)
        dimension_matches.extend(
            left.dimension_decisions[name] == right.dimension_decisions[name]
            for name in sorted(shared_dimensions)
        )
        left_chunks = set(left.verified_chunk_ids)
        right_chunks = set(right.verified_chunk_ids)
        if left_chunks or right_chunks:
            evidence_exact.append(left_chunks == right_chunks)
            union = left_chunks | right_chunks
            evidence_jaccard.append(len(left_chunks & right_chunks) / len(union))

    return HumanReviewAgreement(
        total_case_count=len(reviews_by_case),
        second_review_case_count=len(pairs),
        second_review_rate=len(pairs) / len(reviews_by_case),
        status_exact_agreement=sum(
            left == right for left, right in zip(left_statuses, right_statuses)
        ) / len(pairs),
        status_cohen_kappa=_cohen_kappa(left_statuses, right_statuses),
        dimension_comparison_count=len(dimension_matches),
        dimension_exact_agreement=(
            sum(dimension_matches) / len(dimension_matches)
            if dimension_matches
            else None
        ),
        evidence_mapping_case_count=len(evidence_exact),
        evidence_mapping_exact_agreement=(
            sum(evidence_exact) / len(evidence_exact)
            if evidence_exact
            else None
        ),
        evidence_mapping_mean_jaccard=(
            sum(evidence_jaccard) / len(evidence_jaccard)
            if evidence_jaccard
            else None
        ),
        excluded_case_ids=excluded_case_ids,
    )


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


def paired_bootstrap_difference(
    baseline_scores: Mapping[str, float],
    agentic_scores: Mapping[str, float],
    confidence_level: float = 0.95,
    bootstrap_samples: int = 10000,
    seed: int = 42,
) -> PairedDifferenceSummary:
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if bootstrap_samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    if set(baseline_scores) != set(agentic_scores):
        missing_baseline = sorted(set(agentic_scores) - set(baseline_scores))
        missing_agentic = sorted(set(baseline_scores) - set(agentic_scores))
        raise ValueError(
            "paired scores require identical case IDs; "
            f"missing baseline={missing_baseline}, missing agentic={missing_agentic}"
        )
    if not baseline_scores:
        raise ValueError("paired scores cannot be empty")

    differences = [
        float(agentic_scores[case_id]) - float(baseline_scores[case_id])
        for case_id in sorted(baseline_scores)
    ]
    mean_difference = sum(differences) / len(differences)
    rng = random.Random(seed)
    bootstrap_means = []
    for _ in range(bootstrap_samples):
        sample = [differences[rng.randrange(len(differences))] for _ in differences]
        bootstrap_means.append(sum(sample) / len(sample))
    bootstrap_means.sort()
    alpha = 1.0 - confidence_level
    return PairedDifferenceSummary(
        case_count=len(differences),
        mean_difference=mean_difference,
        ci_low=_quantile(bootstrap_means, alpha / 2),
        ci_high=_quantile(bootstrap_means, 1 - alpha / 2),
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )


def paired_clustered_pooled_bootstrap_difference(
    baseline_point_outcomes: Mapping[str, Sequence[bool]],
    agentic_point_outcomes: Mapping[str, Sequence[bool]],
    confidence_level: float = 0.95,
    bootstrap_samples: int = 10000,
    seed: int = 42,
) -> PairedDifferenceSummary:
    """Bootstrap a pooled point metric while preserving case-level clustering.

    Each draw resamples whole cases. Point outcomes inside each selected case stay
    together, and the score is recomputed as passed points / scorable points.
    """
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if bootstrap_samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    if set(baseline_point_outcomes) != set(agentic_point_outcomes):
        raise ValueError("paired point outcomes require identical case IDs")
    if not baseline_point_outcomes:
        raise ValueError("paired point outcomes cannot be empty")

    case_ids = sorted(baseline_point_outcomes)
    for case_id in case_ids:
        if len(baseline_point_outcomes[case_id]) != len(agentic_point_outcomes[case_id]):
            raise ValueError(f"paired point outcomes require equal point counts for {case_id}")
    if not any(baseline_point_outcomes[case_id] for case_id in case_ids):
        raise ValueError("paired point outcomes require at least one scorable point")

    def pooled_difference(sampled_case_ids: Sequence[str]) -> float:
        baseline_total = sum(len(baseline_point_outcomes[case_id]) for case_id in sampled_case_ids)
        agentic_total = sum(len(agentic_point_outcomes[case_id]) for case_id in sampled_case_ids)
        if baseline_total != agentic_total or baseline_total == 0:
            raise ValueError("paired sampled cases must contain matching scorable point totals")
        baseline_passed = sum(
            sum(bool(point) for point in baseline_point_outcomes[case_id])
            for case_id in sampled_case_ids
        )
        agentic_passed = sum(
            sum(bool(point) for point in agentic_point_outcomes[case_id])
            for case_id in sampled_case_ids
        )
        return (agentic_passed - baseline_passed) / baseline_total

    mean_difference = pooled_difference(case_ids)
    rng = random.Random(seed)
    bootstrap_differences = []
    for _ in range(bootstrap_samples):
        sample = [case_ids[rng.randrange(len(case_ids))] for _ in case_ids]
        bootstrap_differences.append(pooled_difference(sample))
    bootstrap_differences.sort()
    alpha = 1.0 - confidence_level
    return PairedDifferenceSummary(
        case_count=len(case_ids),
        mean_difference=mean_difference,
        ci_low=_quantile(bootstrap_differences, alpha / 2),
        ci_high=_quantile(bootstrap_differences, 1 - alpha / 2),
        confidence_level=confidence_level,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
    )


def mcnemar_exact(
    baseline_outcomes: Mapping[str, bool],
    agentic_outcomes: Mapping[str, bool],
) -> McNemarResult:
    if set(baseline_outcomes) != set(agentic_outcomes):
        raise ValueError("McNemar test requires identical paired case IDs")
    a_only = sum(
        bool(baseline_outcomes[case_id]) and not bool(agentic_outcomes[case_id])
        for case_id in baseline_outcomes
    )
    b_only = sum(
        bool(agentic_outcomes[case_id]) and not bool(baseline_outcomes[case_id])
        for case_id in baseline_outcomes
    )
    discordant = a_only + b_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, value) * (0.5 ** discordant)
            for value in range(0, min(a_only, b_only) + 1)
        )
        p_value = min(1.0, 2 * tail)
    return McNemarResult(
        discordant_a_only=a_only,
        discordant_b_only=b_only,
        exact_two_sided_p_value=p_value,
    )
