import json
from types import SimpleNamespace

import pytest

from app.evaluation.benchmark_judge import LLMBenchmarkJudge, build_judge_prompt
from app.evaluation.source_registry import SourceRegistry, build_source_registry
from tests.evaluation_helpers import SNAPSHOT_DATE, answerable_case


def _registry():
    records, _, _ = build_source_registry(
        [{
            "chunk_id": "chunk-main",
            "document_id": "main",
            "source_path": "data/raw/rules/main_board.pdf",
            "rule_number": "14.34",
            "text": "Main Board Rule 14.34 requires an issuer announcement with sufficient details.",
        }],
        snapshot_date=SNAPSHOT_DATE,
        min_text_chars=20,
    )
    return SourceRegistry(records)


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_judge_prompt_is_stable_and_contains_only_declared_sources():
    case = answerable_case()
    prompt_one, hash_one = build_judge_prompt(case, _registry())
    prompt_two, hash_two = build_judge_prompt(case, _registry())

    assert prompt_one == prompt_two
    assert hash_one == hash_two
    assert "chunk-main" in prompt_one
    assert "Return one JSON object" in prompt_one


def test_llm_judge_uses_shared_shape_and_strict_json():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })
    completions = _FakeCompletions(content)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    assert assessment.judge_model == "independent-judge"
    assert assessment.source_support == 5
    assert completions.kwargs["temperature"] == 0.0
    assert completions.kwargs["response_format"] == {"type": "json_object"}


def test_llm_judge_accepts_json_followed_by_model_notes():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported",
        }],
        "issues": [],
        "judge_reason": "Valid",
    }) + "\nModel note: validated."
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(content)))

    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    assert assessment.source_support == 5


def test_llm_judge_uses_reasoning_content_when_content_is_empty():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })

    class _ReasoningOnlyCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="", reasoning_content=content,
            ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_ReasoningOnlyCompletions()))
    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    assert assessment.answer_points_grounded == 5


def test_llm_judge_normalizes_the_common_score_based_response_shape():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": 5,
        "no_unsupported_claims": 5,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "evaluation": 5,
            "grounded": True,
            "notes": "The source supports the point.",
            "reason": "Supported by the mapped source.",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(content)))

    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    point = assessment.answer_point_results[0]
    assert assessment.language_correct is True
    assert assessment.no_unsupported_claims is True
    assert point.supported is True
    assert point.supporting_chunk_ids == ["chunk-main"]


def test_llm_judge_normalizes_support_score_alias_for_answer_points():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "support": 5,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported by the mapped source.",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(content)))

    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    assert assessment.answer_point_results[0].supported is True


def test_llm_judge_prefers_the_field_that_contains_json_over_thinking_text():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })

    class _ThinkingAndJsonCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content="I will now evaluate the supplied evidence.",
                reasoning_content=content,
            ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_ThinkingAndJsonCompletions()))
    assessment = LLMBenchmarkJudge(model="independent-judge", client=client).assess(
        case, _registry()
    )

    assert assessment.source_support == 5


def test_llm_judge_retries_an_empty_response_before_accepting_json():
    case = answerable_case()
    content = json.dumps({
        "source_support": 5,
        "expected_rules_valid": 5,
        "answer_points_grounded": 5,
        "category_fit": 5,
        "difficulty_fit": 5,
        "language_correct": True,
        "no_unsupported_claims": True,
        "answer_point_results": [{
            "point_id": case.answer_points[0].point_id,
            "supported": True,
            "supporting_chunk_ids": ["chunk-main"],
            "reason": "Supported",
        }],
        "issues": [],
        "judge_reason": "Valid",
    })

    class _RetryingCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            value = "" if self.calls == 1 else content
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])

    completions = _RetryingCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    assessment = LLMBenchmarkJudge(
        model="independent-judge", client=client, max_attempts=2,
    ).assess(case, _registry())

    assert assessment.source_support == 5
    assert completions.calls == 2


def test_llm_judge_rejects_same_model_as_generator():
    case = answerable_case()
    with pytest.raises(ValueError, match="must differ"):
        LLMBenchmarkJudge(model=case.provenance.generator_model, client=object()).assess(
            case, _registry()
        )


def test_llm_judge_reports_an_invalid_json_response_after_bounded_retries():
    case = answerable_case()
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions("{invalid json")))

    with pytest.raises(ValueError, match="after 2 attempts"):
        LLMBenchmarkJudge(
            model="independent-judge", client=client, max_attempts=2,
        ).assess(case, _registry())
