from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class RuleSet(str, Enum):
    MAIN_BOARD = "main_board"
    GEM = "gem"
    GUIDANCE = "guidance"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class CaseType(str, Enum):
    ANSWERABLE = "answerable"
    TOOL = "tool"
    MULTI_TURN = "multi_turn"
    NEGATIVE = "negative"


class Language(str, Enum):
    ENGLISH = "en"
    CHINESE = "zh"
    MIXED = "mixed"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class PrimaryCategory(str, Enum):
    RULE_LOOKUP = "rule_lookup"
    OBLIGATION_SUMMARY = "obligation_summary"
    PROCEDURE_FLOW = "procedure_flow"
    COMPARISON_MULTI_HOP = "comparison_multi_hop"
    SIZE_TEST_CALCULATION = "size_test_calculation"
    TOOL_CHAIN = "tool_chain"
    MULTI_TURN_FOLLOW_UP = "multi_turn_follow_up"
    NEGATIVE_INSUFFICIENT = "negative_insufficient"


class ExpectedIntent(str, Enum):
    RULE_LOOKUP = "rule_lookup"
    OBLIGATION_SUMMARY = "obligation_summary"
    COMPARISON = "comparison"
    ELIGIBILITY_CHECK = "eligibility_check"
    PROCEDURE_FLOW = "procedure_flow"
    CALCULATION_REQUIRED = "calculation_required"
    MULTI_CONDITION = "multi_condition"
    GENERAL = "general"


class RouteMode(str, Enum):
    RETRIEVAL = "retrieval"
    TOOL_ONLY = "tool_only"
    TOOL_PLUS_RETRIEVAL = "tool_plus_retrieval"


class EvidenceKind(str, Enum):
    SOURCE = "source"
    TOOL = "tool"
    EXPECTED_BEHAVIOR = "expected_behavior"


class NegativeReason(str, Enum):
    NONEXISTENT_RULE = "nonexistent_rule"
    INSUFFICIENT_TOOL_INPUTS = "insufficient_tool_inputs"
    AMBIGUOUS_QUERY = "ambiguous_query"
    OUT_OF_SCOPE = "out_of_scope"
    FALSE_PREMISE = "false_premise"


class ExpectedAction(str, Enum):
    ANSWER = "answer"
    ASK_CLARIFICATION = "ask_clarification"
    REFUSE = "refuse"
    STATE_INSUFFICIENT_EVIDENCE = "state_insufficient_evidence"
    CORRECT_PREMISE = "correct_premise"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"


class RowType(str, Enum):
    SINGLE_TURN = "single_turn"
    TURN = "turn"
    AGGREGATE = "aggregate"


class SourceRecord(StrictModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    text: str
    rule_number: Optional[str] = None
    chapter: Optional[str] = None
    section_title: Optional[str] = None
    ruleset: RuleSet = RuleSet.UNKNOWN
    status: SourceStatus = SourceStatus.UNKNOWN
    snapshot_date: date
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    content_hash: str = Field(min_length=64, max_length=64)
    canonical_text_hash: str = Field(min_length=64, max_length=64)
    duplicate_of: Optional[str] = None
    eligible_main_benchmark: bool = False
    eligible_stress: bool = True
    exclusion_reasons: List[str] = Field(default_factory=list)


class CorpusSnapshotManifest(StrictModel):
    snapshot_id: str
    snapshot_date: date
    created_at: datetime = Field(default_factory=utc_now)
    source_path: str
    source_sha256: str = Field(min_length=64, max_length=64)
    policy_version: str
    total_chunks: int = Field(ge=0)
    main_eligible_chunks: int = Field(ge=0)
    excluded_chunks: int = Field(ge=0)
    stress_eligible_chunks: int = Field(ge=0)
    duplicate_groups: int = Field(ge=0)
    chunks_in_duplicate_groups: int = Field(ge=0)
    status_counts: Dict[str, int] = Field(default_factory=dict)
    ruleset_counts: Dict[str, int] = Field(default_factory=dict)
    exclusion_reason_counts: Dict[str, int] = Field(default_factory=dict)


class RuleReference(StrictModel):
    ruleset: RuleSet
    rule_number: str = Field(min_length=1)
    supporting_chunk_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ruleset(self) -> "RuleReference":
        if self.ruleset in {RuleSet.UNKNOWN, RuleSet.NOT_APPLICABLE}:
            raise ValueError("rule references require a concrete ruleset")
        return self


class AnswerPoint(StrictModel):
    point_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_kind: EvidenceKind = EvidenceKind.SOURCE
    supporting_chunk_ids: List[str] = Field(default_factory=list)
    supporting_rules: List[RuleReference] = Field(default_factory=list)
    supporting_tool_call_orders: List[int] = Field(default_factory=list)
    required: bool = True

    @model_validator(mode="after")
    def validate_evidence_mapping(self) -> "AnswerPoint":
        if self.evidence_kind == EvidenceKind.SOURCE and not self.supporting_chunk_ids:
            raise ValueError("source-backed answer points require supporting_chunk_ids")
        if self.evidence_kind == EvidenceKind.TOOL and not self.supporting_tool_call_orders:
            raise ValueError("tool-backed answer points require supporting_tool_call_orders")
        if self.evidence_kind == EvidenceKind.EXPECTED_BEHAVIOR:
            if self.supporting_chunk_ids or self.supporting_tool_call_orders:
                raise ValueError("expected-behavior points cannot claim source or tool support")
        return self


class ExpectedToolCall(StrictModel):
    order: int = Field(ge=1)
    tool_name: str = Field(min_length=1)
    inputs: Dict[str, Any]
    expected_output: Dict[str, Any] = Field(default_factory=dict)
    numeric_tolerances: Dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tolerances(self) -> "ExpectedToolCall":
        if any(value < 0 for value in self.numeric_tolerances.values()):
            raise ValueError("numeric tolerances must be non-negative")
        return self


class NegativeExpectation(StrictModel):
    reason: NegativeReason
    expected_action: ExpectedAction
    missing_inputs: List[str] = Field(default_factory=list)
    target_tool_name: Optional[str] = None
    provided_tool_inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_message_points: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reason_action(self) -> "NegativeExpectation":
        if self.reason == NegativeReason.INSUFFICIENT_TOOL_INPUTS:
            if self.expected_action != ExpectedAction.ASK_CLARIFICATION:
                raise ValueError("insufficient tool inputs must ask for clarification")
            if not self.missing_inputs:
                raise ValueError("insufficient tool inputs require missing_inputs")
            if not self.target_tool_name:
                raise ValueError("insufficient tool inputs require target_tool_name")
        if self.reason == NegativeReason.FALSE_PREMISE:
            if self.expected_action != ExpectedAction.CORRECT_PREMISE:
                raise ValueError("false-premise cases must correct the premise")
        if self.reason == NegativeReason.OUT_OF_SCOPE:
            if self.expected_action not in {ExpectedAction.REFUSE, ExpectedAction.STATE_INSUFFICIENT_EVIDENCE}:
                raise ValueError("out-of-scope cases must refuse or state insufficient evidence")
        return self


class GenerationProvenance(StrictModel):
    generator_model: str
    generator_prompt_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    generated_at: datetime = Field(default_factory=utc_now)
    source_snapshot_id: str
    source_snapshot_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    random_seed: Optional[int] = None


class BenchmarkTurn(StrictModel):
    turn_index: int = Field(ge=1)
    query: str = Field(min_length=1)
    expected_intent: ExpectedIntent
    expected_route: RouteMode
    answer_points: List[AnswerPoint] = Field(default_factory=list)
    expected_tool_calls: List[ExpectedToolCall] = Field(default_factory=list)
    negative_expectation: Optional[NegativeExpectation] = None
    depends_on_turn: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_turn(self) -> "BenchmarkTurn":
        orders = [call.order for call in self.expected_tool_calls]
        if len(orders) != len(set(orders)):
            raise ValueError("tool call order values must be unique within a turn")
        if self.depends_on_turn is not None and self.depends_on_turn >= self.turn_index:
            raise ValueError("depends_on_turn must refer to an earlier turn")
        return self


class BenchmarkCase(StrictModel):
    case_id: str = Field(min_length=1)
    case_type: CaseType
    query: Optional[str] = None
    language: Language
    primary_category: PrimaryCategory
    capability_tags: List[str] = Field(default_factory=list)
    difficulty: Difficulty
    as_of: date
    expected_intent: Optional[ExpectedIntent] = None
    expected_route: Optional[RouteMode] = None
    answer_points: List[AnswerPoint] = Field(default_factory=list)
    expected_rules: List[RuleReference] = Field(default_factory=list)
    expected_tool_calls: List[ExpectedToolCall] = Field(default_factory=list)
    negative_expectation: Optional[NegativeExpectation] = None
    turns: List[BenchmarkTurn] = Field(default_factory=list)
    source_chunk_ids: List[str] = Field(default_factory=list)
    provenance: GenerationProvenance
    notes: Optional[str] = None

    def content_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def validate_case_shape(self) -> "BenchmarkCase":
        if self.case_type == CaseType.MULTI_TURN:
            if len(self.turns) < 2:
                raise ValueError("multi-turn cases require at least two turns")
            indices = [turn.turn_index for turn in self.turns]
            if indices != list(range(1, len(indices) + 1)):
                raise ValueError("multi-turn indices must be consecutive and start at 1")
        else:
            if not self.query or not self.query.strip():
                raise ValueError("single-turn cases require query")
            if self.turns:
                raise ValueError("only multi-turn cases may contain turns")
            if self.expected_intent is None or self.expected_route is None:
                raise ValueError("single-turn cases require expected_intent and expected_route")

        if self.case_type == CaseType.TOOL and not self.expected_tool_calls:
            raise ValueError("tool cases require expected_tool_calls")
        if self.case_type == CaseType.NEGATIVE and self.negative_expectation is None:
            raise ValueError("negative cases require negative_expectation")
        if self.case_type != CaseType.NEGATIVE and self.negative_expectation is not None:
            raise ValueError("negative_expectation is only valid for negative cases")

        all_points = list(self.answer_points)
        all_tool_calls = list(self.expected_tool_calls)
        for turn in self.turns:
            all_points.extend(turn.answer_points)
            all_tool_calls.extend(turn.expected_tool_calls)

        source_ids = set(self.source_chunk_ids)
        mapped_source_ids = {
            chunk_id
            for point in all_points
            for chunk_id in point.supporting_chunk_ids
        }
        mapped_source_ids.update(
            chunk_id
            for rule in self.expected_rules
            for chunk_id in rule.supporting_chunk_ids
        )
        mapped_source_ids.update(
            chunk_id
            for point in all_points
            for rule in point.supporting_rules
            for chunk_id in rule.supporting_chunk_ids
        )
        if not mapped_source_ids.issubset(source_ids):
            missing = sorted(mapped_source_ids - source_ids)
            raise ValueError(f"supporting chunks missing from source_chunk_ids: {missing}")

        orders = [call.order for call in all_tool_calls]
        if self.case_type != CaseType.MULTI_TURN and len(orders) != len(set(orders)):
            raise ValueError("tool call order values must be unique")

        if self.case_type == CaseType.NEGATIVE:
            reason = self.negative_expectation.reason
            if reason == NegativeReason.FALSE_PREMISE and not self.answer_points:
                raise ValueError("false-premise cases require corrective answer points")
            if reason in {NegativeReason.NONEXISTENT_RULE, NegativeReason.OUT_OF_SCOPE}:
                source_points = [p for p in self.answer_points if p.evidence_kind == EvidenceKind.SOURCE]
                if source_points:
                    raise ValueError("nonexistent-rule and out-of-scope cases cannot require source-backed answers")

        return self


class AnswerPointJudgeResult(StrictModel):
    point_id: str
    supported: bool
    supporting_chunk_ids: List[str] = Field(default_factory=list)
    reason: str


class JudgeAssessment(StrictModel):
    case_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    judge_model: str
    judge_prompt_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    rubric_version: str = "1.0"
    source_support: Optional[int] = Field(default=None, ge=1, le=5)
    expected_rules_valid: Optional[int] = Field(default=None, ge=1, le=5)
    answer_points_grounded: Optional[int] = Field(default=None, ge=1, le=5)
    category_fit: int = Field(ge=1, le=5)
    difficulty_fit: int = Field(ge=1, le=5)
    language_correct: bool
    no_unsupported_claims: bool
    answer_point_results: List[AnswerPointJudgeResult] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    judge_reason: str
    created_at: datetime = Field(default_factory=utc_now)

    def passes(self, required_point_ids: List[str], threshold: int = 4) -> bool:
        scored = [score for score in (
            self.source_support,
            self.expected_rules_valid,
            self.answer_points_grounded,
            self.category_fit,
            self.difficulty_fit,
        ) if score is not None]
        point_results = {result.point_id: result for result in self.answer_point_results}
        required_supported = all(
            point_id in point_results and point_results[point_id].supported
            for point_id in required_point_ids
        )
        return (
            bool(scored)
            and all(score >= threshold for score in scored)
            and self.language_correct
            and self.no_unsupported_claims
            and required_supported
        )


class HumanReview(StrictModel):
    case_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reviewer_id: str = Field(min_length=1)
    status: ReviewStatus
    reviewed_at: datetime = Field(default_factory=utc_now)
    verified_dimensions: List[str] = Field(default_factory=list)
    dimension_decisions: Dict[str, bool] = Field(default_factory=dict)
    verified_chunk_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    second_review: bool = False
    adjudicates_reviewers: List[str] = Field(default_factory=list)


class ValidationCheck(StrictModel):
    check_name: str
    status: CheckStatus
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ValidationRecord(StrictModel):
    case_id: str
    case_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    checks: List[ValidationCheck]
    judge_assessment: Optional[JudgeAssessment] = None
    human_reviews: List[HumanReview] = Field(default_factory=list)
    acceptance_policy_version: str = "1.0"
    accepted: bool = False
    rejection_reasons: List[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def derive_acceptance(self) -> "ValidationRecord":
        required_check_names = {
            "schema",
            "source_snapshot",
            "language",
            "source_eligibility",
            "answer_point_mapping",
            "rule_references",
            "case_type_profile",
            "tool_expectations",
            "duplicate_detection",
            "judge_assessment",
            "human_review",
        }
        check_names = [check.check_name for check in self.checks]
        missing_checks = sorted(required_check_names - set(check_names))
        duplicate_checks = sorted({name for name in check_names if check_names.count(name) > 1})
        blocking_checks = [
            check for check in self.checks
            if check.status not in {CheckStatus.PASS, CheckStatus.NOT_APPLICABLE}
        ]
        reviewer_ids = [review.reviewer_id for review in self.human_reviews]
        duplicate_reviewer_ids = sorted({
            reviewer_id
            for reviewer_id in reviewer_ids
            if reviewer_ids.count(reviewer_id) > 1
        })
        known_reviewer_ids = set(reviewer_ids)
        review_integrity_issues: List[str] = []
        if duplicate_reviewer_ids:
            review_integrity_issues.append(
                f"duplicate reviewer IDs: {duplicate_reviewer_ids}"
            )
        if any(review.case_hash != self.case_hash for review in self.human_reviews):
            review_integrity_issues.append("one or more human review hashes do not match the case")
        for review in self.human_reviews:
            targets = set(review.adjudicates_reviewers)
            if review.reviewer_id in targets:
                review_integrity_issues.append(
                    f"reviewer {review.reviewer_id} cannot adjudicate their own review"
                )
            unknown_targets = sorted(targets - known_reviewer_ids)
            if unknown_targets:
                review_integrity_issues.append(
                    f"reviewer {review.reviewer_id} has unknown adjudication targets: "
                    f"{unknown_targets}"
                )
        if any(review.second_review for review in self.human_reviews) and len(known_reviewer_ids) < 2:
            review_integrity_issues.append(
                "a second review requires a distinct primary reviewer"
            )
        judge_hash_matches = (
            self.judge_assessment is not None
            and self.judge_assessment.case_hash == self.case_hash
        )
        adjudicated_reviewer_ids = {
            reviewer_id
            for review in self.human_reviews
            for reviewer_id in review.adjudicates_reviewers
        }
        approved = any(review.status == ReviewStatus.APPROVED for review in self.human_reviews)
        rejected = any(
            review.status == ReviewStatus.REJECTED
            and review.reviewer_id not in adjudicated_reviewer_ids
            for review in self.human_reviews
        )
        derived = (
            not blocking_checks
            and not missing_checks
            and not duplicate_checks
            and self.judge_assessment is not None
            and judge_hash_matches
            and not review_integrity_issues
            and approved
            and not rejected
        )

        reasons = [check.message for check in blocking_checks]
        if missing_checks:
            reasons.append(f"required validation checks are missing: {missing_checks}")
        if duplicate_checks:
            reasons.append(f"validation checks are duplicated: {duplicate_checks}")
        if self.judge_assessment is None:
            reasons.append("structured judge assessment is required")
        elif not judge_hash_matches:
            reasons.append("judge assessment hash does not match the case")
        reasons.extend(review_integrity_issues)
        if not approved:
            reasons.append("human approval is required")
        if rejected:
            reasons.append("a human reviewer rejected the case")

        self.accepted = derived
        self.rejection_reasons = list(dict.fromkeys(reasons))
        return self


class RetrievalRoundRecord(StrictModel):
    round_number: int = Field(ge=1)
    queries: List[str]
    chunk_ids: List[str]
    coverage_before: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage_after: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RunManifest(StrictModel):
    run_id: str
    benchmark_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    source_snapshot_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    index_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    model_id: str
    model_version: Optional[str] = None
    prompt_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    generation_parameters: Dict[str, Any]
    code_revision: str
    configuration_id: Optional[str] = None
    index_manifest_hash: Optional[str] = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = Field(default=None, ge=1)
    provider: Optional[str] = None
    random_seed: Optional[int] = None
    failure_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    release_version: Optional[str] = None
    release_manifest_hash: Optional[str] = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class EvaluationRunRow(StrictModel):
    run_id: str
    case_id: str
    system: str
    row_type: RowType
    query: str
    answer: str
    turn_index: Optional[int] = Field(default=None, ge=1)
    conversation_id: Optional[str] = None
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    route_decision: Optional[Dict[str, Any]] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    verification_result: Optional[Dict[str, Any]] = None
    retrieval_rounds: List[RetrievalRoundRecord] = Field(default_factory=list)
    coverage_before: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage_after: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    answer_before_verification: Optional[str] = None
    answer_after_verification: Optional[str] = None
    perturbation_id: Optional[str] = None
    parent_case_id: Optional[str] = None
    latency_seconds: float = Field(ge=0.0)
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_row_grain(self) -> "EvaluationRunRow":
        if self.row_type == RowType.TURN and self.turn_index is None:
            raise ValueError("turn rows require turn_index")
        if self.row_type != RowType.TURN and self.turn_index is not None:
            raise ValueError("only turn rows may set turn_index")
        if self.perturbation_id and not self.parent_case_id:
            raise ValueError("perturbed rows require parent_case_id")
        return self


class MetricReadiness(StrictModel):
    metric_name: str
    ready: bool
    reasons: List[str] = Field(default_factory=list)
