import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.automated_reviewer import (
    LLMAutomatedReviewer,
    build_automated_review_prompt,
)
from app.evaluation.dataset_loader import write_jsonl
from app.evaluation.schemas import AutomatedReview
from app.evaluation.schemas import ReviewStatus
from tests.evaluation_helpers import answerable_case


def _packet():
    case = answerable_case()
    return {
        "case_id": case.case_id,
        "case_hash": case.content_hash(),
        "category": case.primary_category.value,
        "query": case.query,
        "turns": [],
        "expected_rules": [rule.model_dump(mode="json") for rule in case.expected_rules],
        "answer_points": [point.model_dump(mode="json") for point in case.answer_points],
        "expected_tool_calls": [],
        "negative_expectation": None,
        "sources": [{
            "chunk_id": "chunk-main",
            "ruleset": "main_board",
            "rule_number": "14.34",
            "source_path": "data/raw/rules/main_board.pdf",
            "text": "Main Board Rule 14.34 requires an issuer announcement.",
        }],
        "review_template": {
            "verified_dimensions": ["source_support", "rule_references"],
            "verified_chunk_ids": ["chunk-main"],
        },
    }


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_automated_review_prompt_is_stable_and_explicitly_non_human():
    packet = _packet()
    prompt_one, hash_one = build_automated_review_prompt(packet)
    prompt_two, hash_two = build_automated_review_prompt(packet)

    assert prompt_one == prompt_two
    assert hash_one == hash_two
    assert "not a human reviewer" in prompt_one
    assert "chunk-main" in prompt_one
    assert "negative_insufficient" in prompt_one


def test_llm_automated_reviewer_normalizes_strict_approval():
    packet = _packet()
    completions = _FakeCompletions(json.dumps({
        "status": "APPROVED",
        "verified_dimensions": ["source_support", "rule_references"],
        "verified_chunk_ids": ["chunk-main"],
        "notes": "The declared rule and answer point are supported by the supplied chunk.",
    }))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    review = LLMAutomatedReviewer(
        model="audit-model", client=client, reviewer_id="audit-agent"
    ).review(packet)

    assert review.status == ReviewStatus.APPROVED
    assert review.reviewer_kind == "llm_subagent"
    assert review.review_model == "audit-model"
    assert review.review_prompt_hash
    assert completions.kwargs["temperature"] == 0.0
    assert completions.kwargs["response_format"] == {"type": "json_object"}


def test_llm_automated_reviewer_rejects_partial_approval():
    packet = _packet()
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(json.dumps({
        "status": "approved",
        "verified_dimensions": ["source_support"],
        "verified_chunk_ids": ["chunk-main"],
        "notes": "Only one dimension was checked.",
    }))))

    with pytest.raises(ValueError, match="verify every required dimension"):
        LLMAutomatedReviewer(model="audit-model", client=client, max_attempts=1).review(packet)


def test_resume_does_not_reuse_pending_automated_reviews(tmp_path):
    packet = _packet()
    output = tmp_path / "automated-reviews.jsonl"
    pending = AutomatedReview(
        case_hash=packet["case_hash"],
        reviewer_id="audit-agent",
        reviewer_kind="llm_subagent",
        review_protocol="r2-automated-audit-v1",
        review_model="audit-model",
        review_prompt_hash="a" * 64,
        status=ReviewStatus.PENDING,
        notes="Temporary provider error.",
    )
    write_jsonl(output, [{
        "case_id": packet["case_id"],
        "automated_review": pending.model_dump(mode="json"),
    }])
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_automated_review.py"
    spec = importlib.util.spec_from_file_location("run_automated_review_for_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._load_existing(output, {packet["case_id"]: packet}) == {}
