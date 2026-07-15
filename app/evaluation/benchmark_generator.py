from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from pydantic import Field

from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.sampling import SamplingQuota
from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    BenchmarkTurn,
    CaseType,
    Difficulty,
    EvidenceKind,
    ExpectedAction,
    ExpectedIntent,
    ExpectedToolCall,
    GenerationProvenance,
    Language,
    NegativeExpectation,
    NegativeReason,
    PrimaryCategory,
    RouteMode,
    RuleReference,
    RuleSet,
    SourceRecord,
    StrictModel,
)
from app.evaluation.source_registry import SourceRegistry, normalize_text, sha256_file
from app.tools.disclosure_checklist import DisclosureChecklistTool
from app.tools.size_test_calculator import SizeTestCalculatorTool
from app.tools.transaction_classifier import TransactionClassifierTool


GENERATOR_MODEL = "codex-5.6-terra"
GENERATOR_PROMPT = (
    "Generate source-grounded HKEX benchmark candidates from frozen, eligible evidence. "
    "Keep every claim bound to exact chunk IDs and do not add unstated legal conclusions. "
    "Generate Chinese cases directly from the evidence and mark them cross_lingual "
    "when the cited evidence is not Chinese-only."
)


class CandidateGenerationManifest(StrictModel):
    generator_model: str
    generator_prompt_hash: str = Field(min_length=64, max_length=64)
    source_snapshot_id: str
    source_snapshot_hash: str = Field(min_length=64, max_length=64)
    graph_nodes_sha256: str = Field(min_length=64, max_length=64)
    graph_edges_sha256: str = Field(min_length=64, max_length=64)
    seed: int
    target_multiplier: int = Field(ge=1)
    candidate_count: int = Field(ge=1)
    category_counts: Dict[str, int]
    language_counts: Dict[str, int]
    difficulty_counts: Dict[str, int]
    candidates_sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime


def generator_prompt_hash() -> str:
    return hashlib.sha256(GENERATOR_PROMPT.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _short_excerpt(text: str, limit: int = 360) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    boundary = normalized.rfind(" ", 0, limit)
    return normalized[:boundary if boundary > 100 else limit].rstrip(" ,;:") + "..."


def _anchor(record: SourceRecord) -> str:
    section = normalize_text(record.section_title or "")
    words = [
        word
        for word in re.findall(r"[a-z0-9]{4,}", normalize_text(record.text))
        if word not in {"that", "with", "from", "this", "which", "under", "shall", "rule"}
    ][:12]
    context = " ".join(words)
    return _short_excerpt(f"{section} {context}".strip(), 150)


def _scenario_label(record: SourceRecord, ordinal: int) -> str:
    adjectives = (
        "Harbour", "Cedar", "Jade", "Meridian", "Northstar", "Pearl", "Summit", "Willow",
        "Aster", "Beacon", "Crown", "Delta", "Ember", "Falcon", "Granite", "Horizon",
    )
    nouns = (
        "Acquisition", "Disposal", "Investment", "Restructuring", "Property Project", "Share Issue",
        "Asset Transfer", "Joint Venture", "Financing", "Reorganisation", "Mandate", "Tender",
        "Lease", "Subscription", "Merger", "Listing Plan",
    )
    digest = hashlib.sha256(f"{record.chunk_id}:{ordinal}".encode("utf-8")).digest()
    return f"{adjectives[digest[0] % len(adjectives)]} {nouns[digest[1] % len(nouns)]} {digest[2]:02x}{digest[3]:02x}"


def _rule_reference(record: SourceRecord) -> RuleReference:
    if record.ruleset not in {RuleSet.MAIN_BOARD, RuleSet.GEM} or not record.rule_number:
        raise ValueError(f"source {record.chunk_id} has no concrete Main Board/GEM rule identity")
    return RuleReference(
        ruleset=record.ruleset,
        rule_number=record.rule_number,
        supporting_chunk_ids=[record.chunk_id],
    )


def _source_point(case_id: str, ordinal: int, record: SourceRecord) -> AnswerPoint:
    reference = _rule_reference(record)
    return AnswerPoint(
        point_id=f"{case_id}-evidence-{ordinal}",
        text=(
            f"Evidence excerpt from {record.ruleset.value} Rule {record.rule_number}: "
            f"{_short_excerpt(record.text)}"
        ),
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=[record.chunk_id],
        supporting_rules=[reference],
    )


def _provenance(registry: SourceRegistry, seed: int) -> GenerationProvenance:
    if registry.manifest is None:
        raise ValueError("candidate generation requires a source snapshot manifest")
    return GenerationProvenance(
        generator_model=GENERATOR_MODEL,
        generator_prompt_hash=generator_prompt_hash(),
        generated_at=datetime.now(tz=timezone.utc),
        source_snapshot_id=registry.manifest.snapshot_id,
        source_snapshot_hash=registry.manifest.source_sha256,
        random_seed=seed,
    )


def _case_tags(language: Language, *tags: str) -> List[str]:
    values = list(tags)
    if language == Language.CHINESE:
        values.append("cross_lingual")
    return values


def _single_query(category: PrimaryCategory, language: Language, record: SourceRecord, ordinal: int) -> str:
    anchor = _anchor(record)
    rule = f"{record.ruleset.value.replace('_', ' ')} Rule {record.rule_number}"
    scenario = _scenario_label(record, ordinal)
    if language == Language.CHINESE:
        templates = {
            PrimaryCategory.RULE_LOOKUP: "请根据 {rule} 的证据段落说明该规则涉及什么要求。背景：{anchor}。",
            PrimaryCategory.OBLIGATION_SUMMARY: "请根据 {rule} 的证据段落概括发行人需要注意的披露或合规义务。背景：{anchor}。",
            PrimaryCategory.PROCEDURE_FLOW: "请依据 {rule} 的证据段落整理其中可确认的程序或行动步骤。背景：{anchor}。",
        }
    else:
        templates = {
            PrimaryCategory.RULE_LOOKUP: "What does {rule} state in the evidence passage concerning {anchor}?",
            PrimaryCategory.OBLIGATION_SUMMARY: "Summarize the issuer obligation evidenced by {rule} in the passage concerning {anchor}.",
            PrimaryCategory.PROCEDURE_FLOW: "What procedure or action sequence is evidenced by {rule} in the passage concerning {anchor}?",
        }
    return templates[category].format(rule=rule, anchor=anchor) + f" Transaction context: {scenario}."


def _pair_query(category: PrimaryCategory, language: Language, left: SourceRecord, right: SourceRecord, ordinal: int) -> str:
    left_rule = f"{left.ruleset.value.replace('_', ' ')} Rule {left.rule_number}"
    right_rule = f"{right.ruleset.value.replace('_', ' ')} Rule {right.rule_number}"
    left_scenario = _scenario_label(left, ordinal)
    right_scenario = _scenario_label(right, ordinal)
    if category == PrimaryCategory.MULTI_TURN_FOLLOW_UP:
        raise ValueError("multi-turn queries are constructed separately")
    if language == Language.CHINESE:
        return (
            f"比较 {left_rule} 与 {right_rule} 的证据段落，并说明两者在“{_anchor(left)}”和“{_anchor(right)}”上的可确认联系。"
            f"情境：{left_scenario} 与 {right_scenario}。"
        )
    return (
        f"Compare the evidence passages for {left_rule} and {right_rule}; identify the grounded relationship "
        f"between {_anchor(left)} and {_anchor(right)}. Transaction contexts: {left_scenario}; {right_scenario}."
    )


def _tool_inputs(ordinal: int) -> Dict[str, float | int | str]:
    highest_ratio = (8, 18, 32, 62, 105)[ordinal % 5]
    transaction_type = "disposal" if ordinal % 4 == 0 else "acquisition"
    return {
        "issuer_market_cap": 1000,
        "issuer_total_assets": 2000,
        "issuer_net_assets": 800,
        "issuer_annual_profit": 120,
        "issuer_shares_outstanding": 1000,
        "transaction_consideration": highest_ratio * 10,
        "acquired_assets": highest_ratio * 20,
        "acquired_profit": highest_ratio * 1.2,
        "acquired_net_assets": highest_ratio * 8,
        "consideration_shares": 0,
        "transaction_type": transaction_type,
    }


def _tool_case(
    case_id: str,
    category: PrimaryCategory,
    language: Language,
    difficulty: Difficulty,
    record: SourceRecord,
    ordinal: int,
    registry: SourceRegistry,
    seed: int,
) -> BenchmarkCase:
    size_tool = SizeTestCalculatorTool()
    classifier = TransactionClassifierTool()
    checklist = DisclosureChecklistTool()
    size_inputs = _tool_inputs(ordinal)
    size_output = size_tool.run(size_inputs)
    if "error" in size_output:
        raise RuntimeError(f"generated size-test inputs are invalid: {size_output}")
    if language == Language.CHINESE:
        query = (
            f"请在“{_anchor(record)}”的业务背景下计算 {_scenario_label(record, ordinal)} 的规模测试，"
            "并依据结果说明后续分类与披露步骤。"
        )
    else:
        query = (
            f"In the business context of {_anchor(record)}, calculate the size tests and identify the resulting "
            f"classification and disclosure steps for the {_scenario_label(record, ordinal)}."
        )
    calls = [ExpectedToolCall(
        order=1,
        tool_name="size_test_calculator",
        inputs=size_inputs,
        expected_output=size_output,
        numeric_tolerances={"highest_ratio": 0.01},
    )]
    points = [AnswerPoint(
        point_id=f"{case_id}-size-result",
        text="The size-test output determines the highest ratio and suggested classification.",
        evidence_kind=EvidenceKind.TOOL,
        supporting_tool_call_orders=[1],
    )]
    tags = _case_tags(language, "tool", "size_test")
    if category == PrimaryCategory.TOOL_CHAIN:
        if language == Language.CHINESE:
            query += "请按规模测试、交易分类和披露清单三个连续步骤完成分析。"
        else:
            query += " Complete the chained size-test, transaction-classification, and disclosure-checklist workflow."
        classifier_inputs = {
            "highest_ratio": size_output["highest_ratio"],
            "transaction_type": size_inputs["transaction_type"],
            "is_connected": bool(ordinal % 3 == 0),
        }
        if classifier_inputs["is_connected"]:
            classifier_inputs["connected_party_type"] = "director"
        classifier_output = classifier.run(classifier_inputs)
        checklist_inputs = {
            "classification": classifier_output["classification"],
            "is_connected": classifier_inputs["is_connected"],
            "shareholder_vote_required": classifier_output["shareholder_vote_required"],
        }
        checklist_output = checklist.run(checklist_inputs)
        calls.extend([
            ExpectedToolCall(
                order=2,
                tool_name="transaction_classifier",
                inputs=classifier_inputs,
                expected_output=classifier_output,
            ),
            ExpectedToolCall(
                order=3,
                tool_name="disclosure_checklist",
                inputs=checklist_inputs,
                expected_output=checklist_output,
            ),
        ])
        points.extend([
            AnswerPoint(
                point_id=f"{case_id}-classification-result",
                text="The classification output determines the applicable rule set and approval flags.",
                evidence_kind=EvidenceKind.TOOL,
                supporting_tool_call_orders=[2],
            ),
            AnswerPoint(
                point_id=f"{case_id}-checklist-result",
                text="The checklist output records the required disclosure actions and deadlines.",
                evidence_kind=EvidenceKind.TOOL,
                supporting_tool_call_orders=[3],
            ),
        ])
        tags.append("tool_chain")
    reference = _rule_reference(record)
    return BenchmarkCase(
        case_id=case_id,
        case_type=CaseType.TOOL,
        query=query,
        language=language,
        primary_category=category,
        capability_tags=tags,
        difficulty=difficulty,
        as_of=registry.manifest.snapshot_date,
        expected_intent=ExpectedIntent.CALCULATION_REQUIRED,
        expected_route=RouteMode.TOOL_PLUS_RETRIEVAL,
        answer_points=points,
        expected_rules=[reference],
        expected_tool_calls=calls,
        source_chunk_ids=[record.chunk_id],
        provenance=_provenance(registry, seed),
    )


def _negative_case(
    case_id: str,
    language: Language,
    difficulty: Difficulty,
    ordinal: int,
    registry: SourceRegistry,
    seed: int,
    source: SourceRecord,
) -> BenchmarkCase:
    variant = ordinal % 5
    if variant == 0:
        query = (
            f"In the context of {_anchor(source)}, HKEX Rule 99Z.{ordinal}: what mandatory disclosure does it require?"
            if language == Language.ENGLISH
            else f"就“{_anchor(source)}”的背景而言，HKEX 规则 99Z.{ordinal} 要求哪些强制披露？"
        )
        expectation = NegativeExpectation(
            reason=NegativeReason.NONEXISTENT_RULE,
            expected_action=ExpectedAction.STATE_INSUFFICIENT_EVIDENCE,
            expected_message_points=["The requested rule was not found in the frozen HKEX source snapshot."],
        )
        return _negative_without_source(case_id, language, difficulty, query, expectation, registry, seed, "nonexistent_rule")
    if variant == 1:
        query = (
            f"For {_scenario_label(source, ordinal)} in the context of {_anchor(source)}, calculate the size test without stating whether it is an acquisition or disposal."
            if language == Language.ENGLISH
            else f"在“{_anchor(source)}”的背景下，请计算 {_scenario_label(source, ordinal)} 的规模测试，但没有说明该交易是收购还是出售。"
        )
        expectation = NegativeExpectation(
            reason=NegativeReason.INSUFFICIENT_TOOL_INPUTS,
            expected_action=ExpectedAction.ASK_CLARIFICATION,
            target_tool_name="size_test_calculator",
            provided_tool_inputs={"transaction_consideration": 100},
            missing_inputs=["transaction_type"],
            expected_message_points=["Ask for the transaction type before calculating the classification."],
        )
        return _negative_without_source(case_id, language, difficulty, query, expectation, registry, seed, "missing_tool_input")
    if variant == 2:
        query = (
            f"For {_scenario_label(source, ordinal)} involving {_anchor(source)}, what approvals are needed?"
            if language == Language.ENGLISH
            else f"涉及“{_anchor(source)}”的 {_scenario_label(source, ordinal)} 需要哪些批准？"
        )
        expectation = NegativeExpectation(
            reason=NegativeReason.AMBIGUOUS_QUERY,
            expected_action=ExpectedAction.ASK_CLARIFICATION,
            expected_message_points=["Ask for the transaction type, size, and connected-party context."],
        )
        return _negative_without_source(case_id, language, difficulty, query, expectation, registry, seed, "ambiguous")
    if variant == 3:
        query = (
            f"What does US SEC Rule 144 require for a Hong Kong issuer undertaking the {_scenario_label(source, ordinal)} involving {_anchor(source)}?"
            if language == Language.ENGLISH
            else f"美国 SEC Rule 144 对进行涉及“{_anchor(source)}”的 {_scenario_label(source, ordinal)} 的香港发行人有什么要求？"
        )
        expectation = NegativeExpectation(
            reason=NegativeReason.OUT_OF_SCOPE,
            expected_action=ExpectedAction.REFUSE,
            expected_message_points=["State that the frozen corpus covers HKEX Listing Rules, not US SEC requirements."],
        )
        return _negative_without_source(case_id, language, difficulty, query, expectation, registry, seed, "out_of_scope")

    reference = _rule_reference(source)
    query = (
        f"For the {_scenario_label(source, ordinal)} involving {_anchor(source)}, does {source.ruleset.value.replace('_', ' ')} Rule {source.rule_number} eliminate every disclosure obligation?"
        if language == Language.ENGLISH
        else f"就涉及“{_anchor(source)}”的 {_scenario_label(source, ordinal)} 而言，{source.ruleset.value.replace('_', ' ')} Rule {source.rule_number} 是否免除所有披露义务？"
    )
    return BenchmarkCase(
        case_id=case_id,
        case_type=CaseType.NEGATIVE,
        query=query,
        language=language,
        primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT,
        capability_tags=_case_tags(language, "negative", "false_premise"),
        difficulty=difficulty,
        as_of=registry.manifest.snapshot_date,
        expected_intent=ExpectedIntent.RULE_LOOKUP,
        expected_route=RouteMode.RETRIEVAL,
        answer_points=[_source_point(case_id, 1, source)],
        expected_rules=[reference],
        negative_expectation=NegativeExpectation(
            reason=NegativeReason.FALSE_PREMISE,
            expected_action=ExpectedAction.CORRECT_PREMISE,
            expected_message_points=["Correct the absolute premise using the cited rule evidence."],
        ),
        source_chunk_ids=[source.chunk_id],
        provenance=_provenance(registry, seed),
    )


def _negative_without_source(
    case_id: str,
    language: Language,
    difficulty: Difficulty,
    query: str,
    expectation: NegativeExpectation,
    registry: SourceRegistry,
    seed: int,
    tag: str,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        case_type=CaseType.NEGATIVE,
        query=query,
        language=language,
        primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT,
        capability_tags=_case_tags(language, "negative", tag),
        difficulty=difficulty,
        as_of=registry.manifest.snapshot_date,
        expected_intent=(
            ExpectedIntent.CALCULATION_REQUIRED
            if expectation.reason == NegativeReason.INSUFFICIENT_TOOL_INPUTS
            else ExpectedIntent.GENERAL
        ),
        expected_route=(
            RouteMode.TOOL_ONLY
            if expectation.reason == NegativeReason.INSUFFICIENT_TOOL_INPUTS
            else RouteMode.RETRIEVAL
        ),
        negative_expectation=expectation,
        provenance=_provenance(registry, seed),
    )


def _eligible_rule_sources(registry: SourceRegistry) -> List[SourceRecord]:
    sources = [
        record
        for record in registry.records
        if record.eligible_main_benchmark
        and record.ruleset in {RuleSet.MAIN_BOARD, RuleSet.GEM}
        and record.rule_number
    ]
    if not sources:
        raise ValueError("no eligible Main Board/GEM source records with rule numbers are available")
    return sorted(sources, key=lambda item: item.chunk_id)


def _graph_pairs(
    edges: Iterable[Mapping[str, object]],
    allowed_ids: set[str],
) -> List[Tuple[str, str]]:
    pairs: set[Tuple[str, str]] = set()
    for edge in edges:
        if edge.get("edge_type") not in {
            "rule_reference",
            "same_scenario",
            "semantic_similarity",
            "tool_dependency",
        }:
            continue
        src = str(edge["src"]).removeprefix("chunk:")
        dst = str(edge["dst"]).removeprefix("chunk:")
        if src in allowed_ids and dst in allowed_ids and src != dst:
            pairs.add(tuple(sorted((src, dst))))
    if not pairs:
        raise ValueError("source graph does not contain connected eligible rule-source pairs")
    return sorted(pairs)


def _pick_unused(
    values: Sequence[SourceRecord],
    key: str,
    ordinal: int,
    used: set[str],
) -> SourceRecord:
    ranked = sorted(
        values,
        key=lambda item: hashlib.sha256(f"{key}:{item.chunk_id}".encode("utf-8")).hexdigest(),
    )
    for offset in range(len(ranked)):
        candidate = ranked[(ordinal + offset) % len(ranked)]
        if candidate.chunk_id not in used:
            used.add(candidate.chunk_id)
            return candidate
    raise ValueError(f"source pool exhausted while generating unique candidates for {key}")


def _pick_unused_pair(
    pairs: Sequence[Tuple[str, str]],
    records: Mapping[str, SourceRecord],
    key: str,
    ordinal: int,
    used: set[Tuple[str, str]],
) -> Tuple[SourceRecord, SourceRecord]:
    ranked = sorted(
        pairs,
        key=lambda item: hashlib.sha256(f"{key}:{item[0]}:{item[1]}".encode("utf-8")).hexdigest(),
    )
    for offset in range(len(ranked)):
        pair = ranked[(ordinal + offset) % len(ranked)]
        if pair not in used:
            used.add(pair)
            return records[pair[0]], records[pair[1]]
    raise ValueError(f"connected source-pair pool exhausted while generating {key}")


def generate_candidates(
    registry: SourceRegistry,
    graph_edges: Iterable[Mapping[str, object]],
    quota: SamplingQuota,
    target_multiplier: int = 2,
    seed: int = 42,
) -> List[BenchmarkCase]:
    if target_multiplier < 1:
        raise ValueError("target_multiplier must be at least 1")
    if registry.manifest is None:
        raise ValueError("candidate generation requires a source snapshot manifest")
    sources = _eligible_rule_sources(registry)
    source_by_id = {record.chunk_id: record for record in sources}
    pairs = _graph_pairs(graph_edges, set(source_by_id))
    generated: List[BenchmarkCase] = []
    used_sources: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    used_pairs: set[Tuple[str, str]] = set()
    ordinal = 0

    for cell in sorted(quota.cells, key=lambda item: item.key):
        for index in range(cell.count * target_multiplier):
            ordinal += 1
            case_id = f"terra-{_slug(cell.primary_category.value)}-{cell.language.value}-{cell.difficulty.value}-{index + 1:03d}"
            category = cell.primary_category
            if category == PrimaryCategory.NEGATIVE_INSUFFICIENT:
                source = _pick_unused(
                    sources,
                    f"{category.value}:{cell.language.value}",
                    index,
                    used_sources[(category.value, cell.language.value)],
                )
                generated.append(_negative_case(
                    case_id, cell.language, cell.difficulty, ordinal, registry, seed, source
                ))
                continue
            if category in {PrimaryCategory.SIZE_TEST_CALCULATION, PrimaryCategory.TOOL_CHAIN}:
                source = _pick_unused(
                    sources,
                    f"{category.value}:{cell.language.value}",
                    index,
                    used_sources[(category.value, cell.language.value)],
                )
                generated.append(_tool_case(
                    case_id, category, cell.language, cell.difficulty, source, ordinal, registry, seed
                ))
                continue
            if category in {PrimaryCategory.COMPARISON_MULTI_HOP, PrimaryCategory.MULTI_TURN_FOLLOW_UP}:
                left, right = _pick_unused_pair(
                    pairs,
                    source_by_id,
                    f"{category.value}:{cell.language.value}",
                    index,
                    used_pairs,
                )
                if category == PrimaryCategory.COMPARISON_MULTI_HOP:
                    generated.append(BenchmarkCase(
                        case_id=case_id,
                        case_type=CaseType.ANSWERABLE,
                        query=_pair_query(category, cell.language, left, right, ordinal),
                        language=cell.language,
                        primary_category=category,
                        capability_tags=_case_tags(cell.language, "multi_hop", "connected_subgraph"),
                        difficulty=cell.difficulty,
                        as_of=registry.manifest.snapshot_date,
                        expected_intent=ExpectedIntent.COMPARISON,
                        expected_route=RouteMode.RETRIEVAL,
                        answer_points=[_source_point(case_id, 1, left), _source_point(case_id, 2, right)],
                        expected_rules=[_rule_reference(left), _rule_reference(right)],
                        source_chunk_ids=[left.chunk_id, right.chunk_id],
                        provenance=_provenance(registry, seed),
                    ))
                else:
                    if cell.language == Language.CHINESE:
                        first_query = f"就 {_scenario_label(left, ordinal)}，请根据 {left.ruleset.value.replace('_', ' ')} Rule {left.rule_number} 的证据说明可确认的要求。"
                        second_query = f"基于 {_scenario_label(right, ordinal)} 的关联背景，请再根据 {right.ruleset.value.replace('_', ' ')} Rule {right.rule_number} 的证据说明下一项要求。"
                    else:
                        first_query = f"For the {_scenario_label(left, ordinal)}, what requirement is evidenced by {left.ruleset.value.replace('_', ' ')} Rule {left.rule_number}?"
                        second_query = f"For the related {_scenario_label(right, ordinal)}, what additional requirement is evidenced by {right.ruleset.value.replace('_', ' ')} Rule {right.rule_number}?"
                    generated.append(BenchmarkCase(
                        case_id=case_id,
                        case_type=CaseType.MULTI_TURN,
                        language=cell.language,
                        primary_category=category,
                        capability_tags=_case_tags(cell.language, "multi_turn", "connected_subgraph"),
                        difficulty=cell.difficulty,
                        as_of=registry.manifest.snapshot_date,
                        turns=[
                            BenchmarkTurn(
                                turn_index=1,
                                query=first_query,
                                expected_intent=ExpectedIntent.RULE_LOOKUP,
                                expected_route=RouteMode.RETRIEVAL,
                                answer_points=[_source_point(case_id, 1, left)],
                            ),
                            BenchmarkTurn(
                                turn_index=2,
                                query=second_query,
                                expected_intent=ExpectedIntent.RULE_LOOKUP,
                                expected_route=RouteMode.RETRIEVAL,
                                answer_points=[_source_point(case_id, 2, right)],
                                depends_on_turn=1,
                            ),
                        ],
                        expected_rules=[_rule_reference(left), _rule_reference(right)],
                        source_chunk_ids=[left.chunk_id, right.chunk_id],
                        provenance=_provenance(registry, seed),
                    ))
                continue
            source = _pick_unused(
                sources,
                f"{category.value}:{cell.language.value}",
                index,
                used_sources[(category.value, cell.language.value)],
            )
            generated.append(BenchmarkCase(
                case_id=case_id,
                case_type=CaseType.ANSWERABLE,
                query=_single_query(category, cell.language, source, ordinal),
                language=cell.language,
                primary_category=category,
                capability_tags=_case_tags(cell.language, "source_grounded"),
                difficulty=cell.difficulty,
                as_of=registry.manifest.snapshot_date,
                expected_intent={
                    PrimaryCategory.RULE_LOOKUP: ExpectedIntent.RULE_LOOKUP,
                    PrimaryCategory.OBLIGATION_SUMMARY: ExpectedIntent.OBLIGATION_SUMMARY,
                    PrimaryCategory.PROCEDURE_FLOW: ExpectedIntent.PROCEDURE_FLOW,
                }[category],
                expected_route=RouteMode.RETRIEVAL,
                answer_points=[_source_point(case_id, 1, source)],
                expected_rules=[_rule_reference(source)],
                source_chunk_ids=[source.chunk_id],
                provenance=_provenance(registry, seed),
            ))
    if len({case.case_id for case in generated}) != len(generated):
        raise RuntimeError("candidate generator produced duplicate case IDs")
    return generated


def generate_candidate_files(
    source_registry_path: Path,
    graph_edges_path: Path,
    quota_path: Path,
    output_path: Path,
    manifest_path: Path,
    target_multiplier: int = 2,
    seed: int = 42,
) -> CandidateGenerationManifest:
    registry = SourceRegistry.load(source_registry_path)
    graph_edges = read_jsonl(graph_edges_path)
    quota = SamplingQuota.model_validate(json.loads(Path(quota_path).read_text(encoding="utf-8")))
    candidates = generate_candidates(
        registry,
        graph_edges,
        quota,
        target_multiplier=target_multiplier,
        seed=seed,
    )
    write_jsonl(output_path, candidates)
    graph_stats_path = Path(graph_edges_path).with_name("graph_stats.json")
    graph_stats = json.loads(graph_stats_path.read_text(encoding="utf-8"))
    manifest = CandidateGenerationManifest(
        generator_model=GENERATOR_MODEL,
        generator_prompt_hash=generator_prompt_hash(),
        source_snapshot_id=registry.manifest.snapshot_id,
        source_snapshot_hash=registry.manifest.source_sha256,
        graph_nodes_sha256=graph_stats["nodes_sha256"],
        graph_edges_sha256=graph_stats["edges_sha256"],
        seed=seed,
        target_multiplier=target_multiplier,
        candidate_count=len(candidates),
        category_counts=dict(Counter(case.primary_category.value for case in candidates)),
        language_counts=dict(Counter(case.language.value for case in candidates)),
        difficulty_counts=dict(Counter(case.difficulty.value for case in candidates)),
        candidates_sha256=sha256_file(output_path),
        created_at=datetime.now(tz=timezone.utc),
    )
    write_json(manifest_path, manifest)
    return manifest
