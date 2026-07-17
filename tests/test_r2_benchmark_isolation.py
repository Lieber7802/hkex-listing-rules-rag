from app.evaluation.r2_protocol import validate_benchmark_isolation
from tests.evaluation_helpers import answerable_case


def test_isolation_rejects_a_near_duplicate_question_from_v1():
    reference = answerable_case(case_id="v1-rule", query="What does Main Board Rule 14.34 require?")
    candidate = answerable_case(case_id="v11-rule", query="What does Main Board Rule 14.34 require?")

    report = validate_benchmark_isolation([candidate], [reference])

    assert report.passed is False
    assert report.query_overlap_count == 1


def test_isolation_allows_a_new_question_that_reuses_a_source_chunk():
    reference = answerable_case(case_id="v1-rule", query="What does Main Board Rule 14.34 require?")
    candidate = answerable_case(
        case_id="v11-rule",
        query="Which announcement timing detail is supported by the evidence for Main Board Rule 14.34?",
    )

    report = validate_benchmark_isolation([candidate], [reference])

    assert report.passed is True
    assert report.query_overlap_count == 0
