from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    CaseType,
    CheckStatus,
    EvidenceKind,
    ExpectedToolCall,
    HumanReview,
    JudgeAssessment,
    Language,
    NegativeReason,
    PrimaryCategory,
    ReviewStatus,
    RuleReference,
    RuleSet,
    ValidationCheck,
    ValidationRecord,
)
from app.evaluation.source_registry import SourceRegistry, normalize_text
from app.tools.disclosure_checklist import DisclosureChecklistTool
from app.tools.size_test_calculator import SizeTestCalculatorTool
from app.tools.transaction_classifier import TransactionClassifierTool


JUDGE_RUBRIC_VERSION = "1.0"
JUDGE_SCORE_RUBRIC = {
    1: "unsupported or materially incorrect",
    2: "major gaps or weak fit",
    3: "partially correct but requires revision",
    4: "supported and acceptable with only minor issues",
    5: "fully supported, precise, and unambiguous",
}


@dataclass(frozen=True)
class ValidatorConfig:
    duplicate_threshold: float = 0.90
    judge_threshold: int = 4
    require_independent_judge: bool = True


def _check(name: str, status: CheckStatus, message: str, **details: Any) -> ValidationCheck:
    return ValidationCheck(
        check_name=name,
        status=status,
        message=message,
        details=details,
    )


def _normalized_rule_number(value: str) -> str:
    normalized = value.strip().upper()
    normalized = re.sub(r"^(?:MAIN\s+BOARD|GEM)\s+", "", normalized)
    normalized = re.sub(r"^RULES?\s+", "", normalized)
    return normalized.strip()


def _case_query_text(case: BenchmarkCase) -> str:
    if case.case_type == CaseType.MULTI_TURN:
        return "\n".join(turn.query for turn in case.turns)
    return case.query or ""


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _has_english(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2,}", text))


def _query_similarity(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    sequence = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", left_normalized))
    right_tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", right_normalized))
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return max(sequence, jaccard)


def _compare_expected(
    expected: Any,
    actual: Any,
    tolerances: Mapping[str, float],
    path: str = "",
) -> List[str]:
    errors: List[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '<root>'}: expected object, got {type(actual).__name__}"]
        for key, expected_value in expected.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key not in actual:
                errors.append(f"{child_path}: missing from actual output")
                continue
            errors.extend(_compare_expected(expected_value, actual[key], tolerances, child_path))
        return errors

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected list, got {type(actual).__name__}"]
        if len(expected) != len(actual):
            return [f"{path}: expected {len(expected)} items, got {len(actual)}"]
        for index, expected_value in enumerate(expected):
            errors.extend(
                _compare_expected(expected_value, actual[index], tolerances, f"{path}[{index}]")
            )
        return errors

    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return [f"{path}: expected numeric value {expected!r}, got {actual!r}"]
        tolerance = tolerances.get(path, tolerances.get("*", 1e-9))
        if abs(float(actual) - float(expected)) > tolerance:
            errors.append(
                f"{path}: expected {expected!r} +/- {tolerance}, got {actual!r}"
            )
        return errors

    if expected != actual:
        errors.append(f"{path}: expected {expected!r}, got {actual!r}")
    return errors


class BenchmarkValidator:
    def __init__(
        self,
        source_registry: SourceRegistry,
        config: Optional[ValidatorConfig] = None,
        tools: Optional[Mapping[str, Any]] = None,
    ):
        self.source_registry = source_registry
        self.config = config or ValidatorConfig()
        self.tools = dict(tools or {
            "size_test_calculator": SizeTestCalculatorTool(),
            "transaction_classifier": TransactionClassifierTool(),
            "disclosure_checklist": DisclosureChecklistTool(),
        })

    def validate_case(
        self,
        case: BenchmarkCase,
        accepted_cases: Iterable[BenchmarkCase] = (),
        judge_assessment: Optional[JudgeAssessment] = None,
        human_reviews: Sequence[HumanReview] = (),
    ) -> ValidationRecord:
        checks = [
            _check("schema", CheckStatus.PASS, "case passed strict schema validation"),
            self._validate_snapshot(case),
            self._validate_language(case),
            self._validate_sources(case),
            self._validate_answer_points(case),
            self._validate_rule_references(case),
            self._validate_type_profile(case),
            self._validate_tools(case),
            self._validate_duplicates(case, accepted_cases),
            self._validate_judge(case, judge_assessment),
            self._validate_human_reviews(case, human_reviews),
        ]
        return ValidationRecord(
            case_id=case.case_id,
            case_hash=case.content_hash(),
            checks=checks,
            judge_assessment=judge_assessment,
            human_reviews=list(human_reviews),
        )

    def _all_answer_points(self, case: BenchmarkCase) -> List[AnswerPoint]:
        points = list(case.answer_points)
        for turn in case.turns:
            points.extend(turn.answer_points)
        return points

    def _validate_snapshot(self, case: BenchmarkCase) -> ValidationCheck:
        manifest = self.source_registry.manifest
        if manifest is None:
            return _check(
                "source_snapshot",
                CheckStatus.FAIL,
                "source registry snapshot manifest is required",
            )
        mismatches: Dict[str, Any] = {}
        if case.provenance.source_snapshot_id != manifest.snapshot_id:
            mismatches["snapshot_id"] = {
                "case": case.provenance.source_snapshot_id,
                "registry": manifest.snapshot_id,
            }
        if case.provenance.source_snapshot_hash != manifest.source_sha256:
            mismatches["snapshot_hash"] = {
                "case": case.provenance.source_snapshot_hash,
                "registry": manifest.source_sha256,
            }
        if case.as_of != manifest.snapshot_date:
            mismatches["as_of"] = {
                "case": case.as_of.isoformat(),
                "registry": manifest.snapshot_date.isoformat(),
            }
        if mismatches:
            return _check(
                "source_snapshot",
                CheckStatus.FAIL,
                "case provenance does not match the frozen source registry snapshot",
                mismatches=mismatches,
            )
        return _check(
            "source_snapshot",
            CheckStatus.PASS,
            "case provenance matches the frozen source registry snapshot",
            snapshot_id=manifest.snapshot_id,
        )

    def _all_rule_references(self, case: BenchmarkCase) -> List[RuleReference]:
        references = list(case.expected_rules)
        for point in self._all_answer_points(case):
            references.extend(point.supporting_rules)
        unique: Dict[Tuple[str, str, Tuple[str, ...]], RuleReference] = {}
        for reference in references:
            key = (
                reference.ruleset.value,
                _normalized_rule_number(reference.rule_number),
                tuple(sorted(reference.supporting_chunk_ids)),
            )
            unique[key] = reference
        return list(unique.values())

    def _all_tool_calls(self, case: BenchmarkCase) -> List[ExpectedToolCall]:
        calls = list(case.expected_tool_calls)
        for turn in case.turns:
            calls.extend(turn.expected_tool_calls)
        return calls

    def _validate_language(self, case: BenchmarkCase) -> ValidationCheck:
        text = _case_query_text(case)
        has_chinese = _has_chinese(text)
        has_english = _has_english(text)
        valid = (
            (case.language == Language.CHINESE and has_chinese)
            or (case.language == Language.ENGLISH and not has_chinese)
            or (case.language == Language.MIXED and has_chinese and has_english)
        )
        if valid:
            return _check("language", CheckStatus.PASS, "language label matches query text")
        return _check(
            "language",
            CheckStatus.FAIL,
            "language label does not match query text",
            expected=case.language.value,
            has_chinese=has_chinese,
            has_english=has_english,
        )

    def _source_optional(self, case: BenchmarkCase) -> bool:
        if case.case_type != CaseType.NEGATIVE or case.negative_expectation is None:
            return False
        return case.negative_expectation.reason in {
            NegativeReason.NONEXISTENT_RULE,
            NegativeReason.INSUFFICIENT_TOOL_INPUTS,
            NegativeReason.AMBIGUOUS_QUERY,
            NegativeReason.OUT_OF_SCOPE,
        }

    def _validate_sources(self, case: BenchmarkCase) -> ValidationCheck:
        if not case.source_chunk_ids:
            if self._source_optional(case) or (
                case.case_type == CaseType.TOOL
                and all(point.evidence_kind == EvidenceKind.TOOL for point in self._all_answer_points(case))
            ):
                return _check(
                    "source_eligibility",
                    CheckStatus.NOT_APPLICABLE,
                    "this case profile does not require source-backed gold evidence",
                )
            return _check(
                "source_eligibility",
                CheckStatus.FAIL,
                "case requires at least one source chunk",
            )

        missing: List[str] = []
        ineligible: Dict[str, List[str]] = {}
        for chunk_id in case.source_chunk_ids:
            record = self.source_registry.get(chunk_id)
            if record is None:
                missing.append(chunk_id)
            elif not record.eligible_main_benchmark:
                ineligible[chunk_id] = record.exclusion_reasons

        if missing or ineligible:
            return _check(
                "source_eligibility",
                CheckStatus.FAIL,
                "one or more gold sources are missing or ineligible",
                missing=missing,
                ineligible=ineligible,
            )
        return _check(
            "source_eligibility",
            CheckStatus.PASS,
            "all referenced gold sources are main-benchmark eligible",
            source_count=len(case.source_chunk_ids),
        )

    def _validate_answer_points(self, case: BenchmarkCase) -> ValidationCheck:
        points = self._all_answer_points(case)
        if not points:
            if self._source_optional(case):
                return _check(
                    "answer_point_mapping",
                    CheckStatus.NOT_APPLICABLE,
                    "negative case is validated through expected behavior",
                )
            return _check(
                "answer_point_mapping",
                CheckStatus.FAIL,
                "answerable cases require structured answer points",
            )

        errors: List[str] = []
        source_ids = set(case.source_chunk_ids)
        tool_orders = {call.order for call in self._all_tool_calls(case)}
        seen_ids: set[str] = set()
        for point in points:
            if point.point_id in seen_ids:
                errors.append(f"duplicate answer point id: {point.point_id}")
            seen_ids.add(point.point_id)
            if point.evidence_kind == EvidenceKind.SOURCE and point.text.rstrip().endswith("..."):
                errors.append(
                    f"{point.point_id}: source-backed answer points cannot end with a truncated excerpt"
                )
            for chunk_id in point.supporting_chunk_ids:
                if chunk_id not in source_ids:
                    errors.append(f"{point.point_id}: source {chunk_id} is not declared by the case")
            for order in point.supporting_tool_call_orders:
                if order not in tool_orders:
                    errors.append(f"{point.point_id}: unknown tool call order {order}")

        if errors:
            return _check(
                "answer_point_mapping",
                CheckStatus.FAIL,
                "answer-point evidence mappings are inconsistent",
                errors=errors,
            )
        return _check(
            "answer_point_mapping",
            CheckStatus.PASS,
            "all answer points map to declared evidence",
            required_points=sum(point.required for point in points),
        )

    def _validate_rule_references(self, case: BenchmarkCase) -> ValidationCheck:
        references = self._all_rule_references(case)
        if not references:
            if self._source_optional(case) or case.case_type == CaseType.TOOL:
                return _check(
                    "rule_references",
                    CheckStatus.NOT_APPLICABLE,
                    "this case profile has no required rule references",
                )
            return _check(
                "rule_references",
                CheckStatus.FAIL,
                "answerable source-backed cases require structured rule references",
            )

        errors: List[str] = []
        declared_source_ids = set(case.source_chunk_ids)
        for reference in references:
            if not reference.supporting_chunk_ids:
                errors.append(f"{reference.rule_number}: no supporting chunks")
                continue
            expected_number = _normalized_rule_number(reference.rule_number)
            for chunk_id in reference.supporting_chunk_ids:
                if chunk_id not in declared_source_ids:
                    errors.append(
                        f"{reference.rule_number}: source {chunk_id} is not declared by the case"
                    )
                    continue
                record = self.source_registry.get(chunk_id)
                if record is None:
                    errors.append(f"{reference.rule_number}: unknown source {chunk_id}")
                    continue
                if not record.eligible_main_benchmark:
                    errors.append(f"{reference.rule_number}: ineligible source {chunk_id}")
                    continue
                if record.ruleset not in {reference.ruleset, RuleSet.GUIDANCE}:
                    errors.append(
                        f"{reference.rule_number}: ruleset {reference.ruleset.value} "
                        f"does not match source {record.ruleset.value}"
                    )
                record_number = _normalized_rule_number(record.rule_number or "")
                if record_number != expected_number and expected_number not in record.text.upper():
                    errors.append(
                        f"{reference.rule_number}: source {chunk_id} does not contain the rule"
                    )

        if errors:
            return _check(
                "rule_references",
                CheckStatus.FAIL,
                "one or more rule references are invalid",
                errors=errors,
            )
        return _check(
            "rule_references",
            CheckStatus.PASS,
            "all rule references preserve ruleset identity and map to eligible sources",
            rule_count=len(references),
        )

    def _validate_type_profile(self, case: BenchmarkCase) -> ValidationCheck:
        expected_case_types = {
            "size_test_calculation": CaseType.TOOL,
            "tool_chain": CaseType.TOOL,
            "multi_turn_follow_up": CaseType.MULTI_TURN,
            "negative_insufficient": CaseType.NEGATIVE,
        }
        expected_case_type = expected_case_types.get(
            case.primary_category.value,
            CaseType.ANSWERABLE,
        )
        if case.case_type != expected_case_type:
            return _check(
                "case_type_profile",
                CheckStatus.FAIL,
                "primary category does not match the required case profile",
                primary_category=case.primary_category.value,
                expected_case_type=expected_case_type.value,
                actual_case_type=case.case_type.value,
            )
        if case.primary_category == PrimaryCategory.COMPARISON_MULTI_HOP:
            comparison_points = [
                point for point in case.answer_points
                if len(set(point.supporting_chunk_ids)) >= 2
            ]
            if len(case.source_chunk_ids) < 2 or not comparison_points:
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "comparison cases require a scoreable answer point grounded in both sources",
                )
        if case.primary_category == PrimaryCategory.MULTI_TURN_FOLLOW_UP:
            follow_ups = [turn for turn in case.turns if turn.depends_on_turn is not None]
            previous_sources = {
                chunk_id
                for turn in case.turns
                if turn.turn_index == 1
                for point in turn.answer_points
                for chunk_id in point.supporting_chunk_ids
            }
            follow_up_points = [
                point
                for turn in follow_ups
                for point in turn.answer_points
                if len(set(point.supporting_chunk_ids)) >= 2
                and previous_sources.intersection(point.supporting_chunk_ids)
            ]
            dependency_markers = ("previous", "above", "just answered", "刚才", "前一", "上述")
            has_explicit_reference = any(
                any(marker in turn.query.casefold() for marker in dependency_markers)
                for turn in follow_ups
            )
            if not follow_ups or not follow_up_points or not has_explicit_reference:
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "multi-turn follow-up cases must explicitly use and score the earlier-turn context",
                )
        if case.primary_category == PrimaryCategory.TOOL_CHAIN:
            classifier_calls = [
                call for call in case.expected_tool_calls
                if call.tool_name == "transaction_classifier"
            ]
            applicable_rules = {
                str(rule).strip().upper()
                for call in classifier_calls
                for rule in call.expected_output.get("applicable_rules", [])
                if str(rule).strip()
            }
            referenced_rules = {
                _normalized_rule_number(reference.rule_number)
                for reference in self._all_rule_references(case)
            }
            normalized_applicable = {
                _normalized_rule_number(rule) for rule in applicable_rules
            }
            if not applicable_rules or not referenced_rules.intersection(normalized_applicable):
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "tool-chain regulatory evidence must match a classifier applicable rule",
                    applicable_rules=sorted(applicable_rules),
                    referenced_rules=sorted(referenced_rules),
                )
        if case.case_type != CaseType.NEGATIVE:
            return _check(
                "case_type_profile",
                CheckStatus.PASS,
                f"{case.case_type.value} case satisfies its structural profile",
            )

        expectation = case.negative_expectation
        if expectation is None:
            return _check(
                "case_type_profile",
                CheckStatus.FAIL,
                "negative case is missing negative_expectation",
            )
        if expectation.reason == NegativeReason.FALSE_PREMISE:
            source_points = [
                point for point in case.answer_points
                if point.evidence_kind == EvidenceKind.SOURCE
            ]
            if not source_points:
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "false-premise cases require source-backed correction points",
                )
        if expectation.reason == NegativeReason.INSUFFICIENT_TOOL_INPUTS:
            tool = self.tools.get(expectation.target_tool_name or "")
            if tool is None:
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "insufficient-input case references an unknown target tool",
                    target_tool=expectation.target_tool_name,
                )
            required = set(tool.input_schema.get("required", []))
            actually_missing = required - set(expectation.provided_tool_inputs)
            declared_missing = set(expectation.missing_inputs)
            if not declared_missing.issubset(actually_missing):
                return _check(
                    "case_type_profile",
                    CheckStatus.FAIL,
                    "declared missing inputs are not missing from the provided tool inputs",
                    declared_missing=sorted(declared_missing),
                    actually_missing=sorted(actually_missing),
                )
        return _check(
            "case_type_profile",
            CheckStatus.PASS,
            f"negative profile {expectation.reason.value} is internally consistent",
        )

    def _run_rule_lookup(self, call: ExpectedToolCall) -> Dict[str, Any]:
        raw = call.inputs.get("rule_number")
        if not isinstance(raw, str) or not raw.strip():
            return {"error": "Missing required field: rule_number"}
        expected = _normalized_rule_number(raw)
        matches = [
            record.chunk_id
            for record in self.source_registry.records
            if record.eligible_main_benchmark
            and _normalized_rule_number(record.rule_number or "") == expected
        ]
        return {
            "rule_found": bool(matches),
            "chunk_ids": sorted(matches),
            "total_chunks": len(matches),
        }

    def _validate_tools(self, case: BenchmarkCase) -> ValidationCheck:
        calls = self._all_tool_calls(case)
        if not calls:
            if case.case_type == CaseType.TOOL:
                return _check(
                    "tool_expectations",
                    CheckStatus.FAIL,
                    "tool case has no expected tool calls",
                )
            return _check(
                "tool_expectations",
                CheckStatus.NOT_APPLICABLE,
                "case does not require deterministic tool validation",
            )

        errors: List[str] = []
        for call in sorted(calls, key=lambda item: item.order):
            if not call.expected_output:
                errors.append(f"tool call {call.order} ({call.tool_name}) has no expected_output")
                continue
            if call.tool_name == "rule_lookup":
                actual = self._run_rule_lookup(call)
            else:
                tool = self.tools.get(call.tool_name)
                if tool is None:
                    errors.append(f"tool call {call.order}: unknown tool {call.tool_name}")
                    continue
                validation_errors = tool.validate_inputs(call.inputs)
                if validation_errors:
                    errors.extend(
                        f"tool call {call.order}: {error}" for error in validation_errors
                    )
                    continue
                actual = tool.run(call.inputs)
            comparison_errors = _compare_expected(
                call.expected_output,
                actual,
                call.numeric_tolerances,
            )
            errors.extend(f"tool call {call.order}: {error}" for error in comparison_errors)

        if errors:
            return _check(
                "tool_expectations",
                CheckStatus.FAIL,
                "expected tool execution does not reproduce",
                errors=errors,
            )
        return _check(
            "tool_expectations",
            CheckStatus.PASS,
            "all expected tool inputs and outputs reproduce",
            tool_calls=len(calls),
        )

    def _validate_duplicates(
        self,
        case: BenchmarkCase,
        accepted_cases: Iterable[BenchmarkCase],
    ) -> ValidationCheck:
        query = _case_query_text(case)
        best_case_id: Optional[str] = None
        best_similarity = 0.0
        tool_signature = self._tool_input_signature(case)
        for existing in accepted_cases:
            if existing.case_id == case.case_id:
                continue
            existing_signature = self._tool_input_signature(existing)
            if tool_signature and existing_signature and tool_signature != existing_signature:
                # Numerically different deterministic tool calls represent distinct tasks even
                # when their user-facing wording follows the same scenario template.
                continue
            similarity = _query_similarity(query, _case_query_text(existing))
            if similarity > best_similarity:
                best_similarity = similarity
                best_case_id = existing.case_id

        if best_similarity >= self.config.duplicate_threshold:
            return _check(
                "duplicate_detection",
                CheckStatus.FAIL,
                "candidate is a near duplicate of an accepted case",
                matched_case_id=best_case_id,
                similarity=round(best_similarity, 6),
                threshold=self.config.duplicate_threshold,
                method="normalized_sequence_or_token_jaccard_v1",
            )
        return _check(
            "duplicate_detection",
            CheckStatus.PASS,
            "candidate is not a near duplicate of accepted cases",
            matched_case_id=best_case_id,
            similarity=round(best_similarity, 6),
            threshold=self.config.duplicate_threshold,
            method="normalized_sequence_or_token_jaccard_v1",
        )

    def _tool_input_signature(self, case: BenchmarkCase) -> Tuple[Tuple[int, str, str], ...]:
        calls = self._all_tool_calls(case)
        if not calls:
            return ()
        return tuple(
            (
                call.order,
                call.tool_name,
                json.dumps(call.inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            for call in sorted(calls, key=lambda item: item.order)
        )

    def _validate_judge(
        self,
        case: BenchmarkCase,
        assessment: Optional[JudgeAssessment],
    ) -> ValidationCheck:
        if assessment is None:
            return _check(
                "judge_assessment",
                CheckStatus.PENDING,
                "structured judge assessment is required",
            )
        if assessment.rubric_version != JUDGE_RUBRIC_VERSION:
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge rubric version does not match the acceptance policy",
                expected=JUDGE_RUBRIC_VERSION,
                actual=assessment.rubric_version,
            )
        if assessment.case_hash != case.content_hash():
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge assessment hash does not match the candidate",
            )
        if (
            self.config.require_independent_judge
            and assessment.judge_model == case.provenance.generator_model
        ):
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge model must differ from the generator model",
            )

        source_backed = bool(case.source_chunk_ids)
        rule_backed = bool(self._all_rule_references(case))
        missing_dimensions: List[str] = []
        if source_backed and assessment.source_support is None:
            missing_dimensions.append("source_support")
        if rule_backed and assessment.expected_rules_valid is None:
            missing_dimensions.append("expected_rules_valid")
        if self._all_answer_points(case) and assessment.answer_points_grounded is None:
            missing_dimensions.append("answer_points_grounded")
        if missing_dimensions:
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge assessment omits required rubric dimensions",
                missing_dimensions=missing_dimensions,
            )

        points_by_id = {
            point.point_id: point for point in self._all_answer_points(case)
        }
        result_ids = [result.point_id for result in assessment.answer_point_results]
        duplicate_result_ids = sorted({
            point_id for point_id in result_ids if result_ids.count(point_id) > 1
        })
        point_mapping_errors: List[str] = []
        if duplicate_result_ids:
            point_mapping_errors.append(
                f"duplicate answer-point judge results: {duplicate_result_ids}"
            )
        for result in assessment.answer_point_results:
            point = points_by_id.get(result.point_id)
            if point is None:
                point_mapping_errors.append(
                    f"unknown answer point in judge result: {result.point_id}"
                )
                continue
            result_sources = set(result.supporting_chunk_ids)
            mapped_sources = set(point.supporting_chunk_ids)
            if point.evidence_kind == EvidenceKind.SOURCE and result.supported:
                if not result_sources:
                    point_mapping_errors.append(
                        f"{result.point_id}: supported source point has no judge evidence"
                    )
                elif not result_sources.issubset(mapped_sources):
                    point_mapping_errors.append(
                        f"{result.point_id}: judge evidence is outside the gold mapping"
                    )
            elif result_sources:
                point_mapping_errors.append(
                    f"{result.point_id}: non-source point cannot cite source chunks"
                )
        if point_mapping_errors:
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge answer-point evidence mappings are invalid",
                errors=point_mapping_errors,
            )

        required_point_ids = [
            point.point_id for point in self._all_answer_points(case) if point.required
        ]
        if not assessment.passes(required_point_ids, self.config.judge_threshold):
            return _check(
                "judge_assessment",
                CheckStatus.FAIL,
                "judge assessment does not meet the explicit acceptance rubric",
                threshold=self.config.judge_threshold,
                rubric=JUDGE_SCORE_RUBRIC,
            )
        return _check(
            "judge_assessment",
            CheckStatus.PASS,
            "judge assessment meets the explicit acceptance rubric",
            threshold=self.config.judge_threshold,
            judge_model=assessment.judge_model,
        )

    def _validate_human_reviews(
        self,
        case: BenchmarkCase,
        reviews: Sequence[HumanReview],
    ) -> ValidationCheck:
        reviewer_ids = [review.reviewer_id for review in reviews]
        duplicate_reviewer_ids = sorted({
            reviewer_id
            for reviewer_id in reviewer_ids
            if reviewer_ids.count(reviewer_id) > 1
        })
        if duplicate_reviewer_ids:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "reviewer IDs must be unique within a case",
                reviewer_ids=duplicate_reviewer_ids,
            )
        known_reviewer_ids = set(reviewer_ids)
        invalid_adjudications: List[str] = []
        for review in reviews:
            targets = set(review.adjudicates_reviewers)
            if review.reviewer_id in targets:
                invalid_adjudications.append(
                    f"{review.reviewer_id}: cannot adjudicate their own review"
                )
            unknown_targets = sorted(targets - known_reviewer_ids)
            if unknown_targets:
                invalid_adjudications.append(
                    f"{review.reviewer_id}: unknown adjudication targets {unknown_targets}"
                )
        if invalid_adjudications:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "human adjudication references are invalid",
                errors=invalid_adjudications,
            )
        adjudicated_reviewer_ids = {
            reviewer_id
            for review in reviews
            for reviewer_id in review.adjudicates_reviewers
        }
        unresolved_rejections = [
            review.reviewer_id
            for review in reviews
            if review.status == ReviewStatus.REJECTED
            and review.reviewer_id not in adjudicated_reviewer_ids
        ]
        if unresolved_rejections:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "a human reviewer rejection remains unresolved",
                reviewer_ids=unresolved_rejections,
            )
        hash_mismatches = [
            review.reviewer_id
            for review in reviews
            if review.case_hash != case.content_hash()
        ]
        if hash_mismatches:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "human review hash does not match the candidate",
                reviewer_ids=hash_mismatches,
            )
        approvals = [review for review in reviews if review.status == ReviewStatus.APPROVED]
        if not approvals:
            return _check(
                "human_review",
                CheckStatus.PENDING,
                "human source/rule approval is required",
            )
        if self._source_optional(case):
            required_dimensions = {"expected_behavior"}
        elif case.case_type == CaseType.TOOL and not case.source_chunk_ids:
            required_dimensions = {"tool_expectations"}
        else:
            required_dimensions = {"source_support", "rule_references"}
        sufficiently_scoped = [
            review
            for review in approvals
            if required_dimensions.issubset(set(review.verified_dimensions))
            and all(review.dimension_decisions.get(name) is True for name in required_dimensions)
        ]
        if not sufficiently_scoped:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "human approval does not cover the required validation dimensions",
                required_dimensions=sorted(required_dimensions),
            )
        if case.source_chunk_ids:
            required_source_ids = set(case.source_chunk_ids)
            evidence_scoped = [
                review
                for review in sufficiently_scoped
                if required_source_ids.issubset(set(review.verified_chunk_ids))
            ]
            if not evidence_scoped:
                return _check(
                    "human_review",
                    CheckStatus.FAIL,
                    "human approval does not record all reviewed source chunks",
                    required_chunk_ids=sorted(required_source_ids),
                )
            sufficiently_scoped = evidence_scoped
        if any(review.second_review for review in reviews) and len(reviewer_ids) < 2:
            return _check(
                "human_review",
                CheckStatus.FAIL,
                "a second review requires a distinct primary reviewer",
            )
        return _check(
            "human_review",
            CheckStatus.PASS,
            "human source/rule approval is recorded",
            reviewer_ids=[review.reviewer_id for review in sufficiently_scoped],
            second_review=any(review.second_review for review in sufficiently_scoped),
        )
