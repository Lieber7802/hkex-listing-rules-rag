import json

import pytest

from app.evaluation.schemas import AutomatedReview, ReviewStatus
from scripts.merge_automated_reviews import merge_reviews
from tests.evaluation_helpers import answerable_case


def _review(case, reviewer_id):
    return {
        "case_id": case.case_id,
        "automated_review": AutomatedReview(
            case_hash=case.content_hash(),
            reviewer_id=reviewer_id,
            reviewer_kind="automated_test",
            review_protocol="test-protocol",
            review_model="test-model",
            review_prompt_hash="a" * 64,
            status=ReviewStatus.APPROVED,
            verified_dimensions=["source_support"],
        ).model_dump(mode="json"),
    }


def test_merge_reviews_rejects_missing_selected_case(tmp_path):
    first = answerable_case(case_id="first")
    second = answerable_case(case_id="second")
    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text(
        json.dumps(_review(first, "reviewer-a")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing selected cases"):
        merge_reviews([first, second], [reviews])
