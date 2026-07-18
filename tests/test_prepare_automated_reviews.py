from app.evaluation.dataset_loader import read_jsonl
from app.evaluation.schemas import JudgeAssessment
from scripts.prepare_automated_reviews import main
from scripts.prepare_automated_reviews import build_automated_reviews
from tests.evaluation_helpers import answerable_case


def test_build_automated_reviews_marks_judge_attestation_as_automated_only():
    case = answerable_case()
    assessment = JudgeAssessment(
        case_hash=case.content_hash(),
        judge_model="independent-judge",
        judge_prompt_hash="1" * 64,
        source_support=5,
        expected_rules_valid=5,
        answer_points_grounded=5,
        category_fit=5,
        difficulty_fit=5,
        language_correct=True,
        no_unsupported_claims=True,
        answer_point_results=[{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-1"],
            "reason": "supported",
        }],
        judge_reason="approved",
    )

    records = build_automated_reviews([case], {case.case_id: assessment}, False)

    assert len(records) == 1
    review = records[0]["automated_review"]
    assert review["reviewer_kind"] == "independent_llm_judge"
    assert review["status"] == "approved"
    assert "human" in review["notes"].lower()


def test_cli_writes_a_judgement_subset_for_exact_release_coverage(tmp_path, monkeypatch):
    case = answerable_case()
    candidates = tmp_path / "candidates.jsonl"
    judgements = tmp_path / "judgements.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    subset = tmp_path / "selected-judgements.jsonl"
    candidates.write_text(case.model_dump_json() + "\n", encoding="utf-8")
    assessment = JudgeAssessment(
        case_hash=case.content_hash(),
        judge_model="independent-judge",
        judge_prompt_hash="1" * 64,
        source_support=5,
        expected_rules_valid=5,
        answer_points_grounded=5,
        category_fit=5,
        difficulty_fit=5,
        language_correct=True,
        no_unsupported_claims=True,
        answer_point_results=[{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-1"],
            "reason": "supported",
        }],
        judge_reason="approved",
    )
    judgements.write_text(
        '{"case_id":"case-001","assessment":' + assessment.model_dump_json() + "}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "prepare_automated_reviews.py",
            "--candidates", str(candidates),
            "--judge-assessments", str(judgements),
            "--output", str(reviews),
            "--selected-judgements-output", str(subset),
        ],
    )

    main()

    assert [row["case_id"] for row in read_jsonl(subset)] == [case.case_id]
