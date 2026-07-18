from app.evaluation.pre_review import select_pre_review_cases
from app.evaluation.sampling import QuotaCell, SamplingQuota
from app.evaluation.schemas import Difficulty, Language, PrimaryCategory
from tests.evaluation_helpers import accepted_validation, answerable_case


def test_frozen_selection_can_replace_a_documented_rejection():
    first = answerable_case(case_id="first", difficulty=Difficulty.EASY)
    replacement = answerable_case(case_id="replacement", difficulty=Difficulty.EASY)
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])

    selected, _ = select_pre_review_cases(
        [replacement],
        [accepted_validation(first), accepted_validation(replacement)],
        quota,
        seed=17,
        review_state="pending_automated_review",
    )

    assert [case.case_id for case in selected] == ["replacement"]
