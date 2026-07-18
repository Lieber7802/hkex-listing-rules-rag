from app.evaluation.pre_review import select_pre_review_cases, static_checks_pass
from app.evaluation.sampling import QuotaCell, SamplingQuota
from app.evaluation.schemas import Difficulty, Language, PrimaryCategory
from tests.evaluation_helpers import accepted_validation, answerable_case


def test_pre_review_selection_keeps_human_approval_pending_and_is_reproducible():
    one = answerable_case(case_id="one", difficulty=Difficulty.EASY)
    two = answerable_case(case_id="two", difficulty=Difficulty.EASY)
    records = [accepted_validation(one), accepted_validation(two)]
    quota = SamplingQuota(cells=[
        QuotaCell(
            primary_category=PrimaryCategory.RULE_LOOKUP,
            language=Language.ENGLISH,
            difficulty=Difficulty.EASY,
            count=1,
        )
    ])

    selected_one, manifest_one = select_pre_review_cases([one, two], records, quota, seed=17)
    selected_two, manifest_two = select_pre_review_cases([one, two], records, quota, seed=17)

    assert [case.case_id for case in selected_one] == [case.case_id for case in selected_two]
    assert manifest_one == manifest_two
    assert manifest_one["review_state"] == "pending_human_approval"
    assert all(static_checks_pass(record) for record in records)
