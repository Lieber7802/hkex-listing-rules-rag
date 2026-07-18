import pytest

from scripts.freeze_automated_evaluation_release import _load_wrapped_case_ids


def test_automated_freeze_allows_multiple_reviews_for_one_case(tmp_path):
    reviews = tmp_path / "reviews.jsonl"
    reviews.write_text(
        '{"case_id":"case-1","automated_review":{}}\n'
        '{"case_id":"case-1","automated_review":{}}\n',
        encoding="utf-8",
    )

    assert _load_wrapped_case_ids(
        reviews,
        "automated_review",
        allow_multiple_per_case=True,
    ) == {"case-1"}


def test_automated_freeze_keeps_judgements_one_per_case(tmp_path):
    judgements = tmp_path / "judgements.jsonl"
    judgements.write_text(
        '{"case_id":"case-1","assessment":{}}\n'
        '{"case_id":"case-1","assessment":{}}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="one unique case_id"):
        _load_wrapped_case_ids(judgements, "assessment")
