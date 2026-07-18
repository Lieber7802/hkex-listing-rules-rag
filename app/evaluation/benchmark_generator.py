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
    "For pure calculation cases, bind answer points to deterministic tool outputs and do not "
    "attach unrelated regulatory evidence. For tool-plus-retrieval cases, use only regulatory "
    "sources that directly address the requested transaction classification or disclosure result. "
    "Generate Chinese cases directly from the evidence and mark them cross_lingual "
    "when the cited evidence is not Chinese-only. Comparison cases must include a "
    "scorable, two-source comparison conclusion rather than two independent summaries. "
    "Multi-turn follow-up cases must make the second turn explicitly depend on the "
    "first-turn answer and must score that cross-turn dependency."
)
_QUALIFIED_RULE_NUMBER_RE = re.compile(r"^\d+[A-Z]?(?:\.\d+[A-Z]?)$", re.IGNORECASE)
_CANONICAL_RULE_FILENAMES = {"main_board.pdf", "gem.pdf"}
_MAX_COMPARISON_PAIR_SIMILARITY = 0.80


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
    excluded_reference_multi_source_count: int = Field(default=0, ge=0)
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


def _scenario_detail(record: SourceRecord, ordinal: int) -> str:
    """Return non-legal commercial context that keeps synthetic tool cases distinct."""
    sectors = (
        "renewable-energy assets", "logistics facilities", "healthcare services", "retail operations",
        "data-centre capacity", "hospitality properties", "industrial equipment", "education services",
        "consumer brands", "financial technology", "telecommunications infrastructure", "media rights",
        "mineral interests", "biotechnology research", "port operations", "construction contracts",
    )
    counterparties = (
        "a regional operator", "an institutional investor", "an unaffiliated vendor", "a strategic buyer",
        "a joint-venture partner", "a family-owned business", "a public-sector customer", "a private fund",
        "an overseas distributor", "a licensed service provider", "an independent developer", "a listed counterparty",
    )
    objectives = (
        "expansion", "portfolio rebalancing", "working-capital efficiency", "market entry",
        "operational consolidation", "technology renewal", "supply-chain resilience", "asset monetisation",
        "capacity planning", "risk diversification", "geographic diversification", "post-merger integration",
    )
    timelines = (
        "an accelerated quarter-end timetable", "a phased twelve-month timetable",
        "a staged implementation timetable", "a board-led approval timetable",
        "a financing-contingent timetable", "a regulatory-filing timetable",
        "a due-diligence timetable", "a post-completion timetable",
    )
    funding = (
        "existing cash resources", "a revolving credit facility", "vendor financing",
        "a co-investment arrangement", "an asset-backed facility", "a private placement",
        "an internal capital allocation", "a staged consideration structure",
    )
    risks = (
        "operational integration review", "customer-retention planning", "supply-chain review",
        "technology migration planning", "property transition review", "licensing readiness review",
        "workforce continuity planning", "cross-border execution review",
    )
    digest = hashlib.sha256(f"{record.chunk_id}:detail:{ordinal}".encode("utf-8")).digest()
    return (
        f"{sectors[digest[0] % len(sectors)]} involving {counterparties[digest[1] % len(counterparties)]} "
        f"for {objectives[digest[2] % len(objectives)]}, with {timelines[digest[3] % len(timelines)]}, "
        f"funded through {funding[digest[4] % len(funding)]}, and subject to {risks[digest[5] % len(risks)]}"
    )


def _rule_reference(record: SourceRecord) -> RuleReference:
    if record.ruleset not in {RuleSet.MAIN_BOARD, RuleSet.GEM} or not record.rule_number:
        raise ValueError(f"source {record.chunk_id} has no concrete Main Board/GEM rule identity")
    return RuleReference(
        ruleset=record.ruleset,
        rule_number=record.rule_number,
        supporting_chunk_ids=[record.chunk_id],
    )


def _multi_source_signature(case: BenchmarkCase) -> tuple[str, ...] | None:
    source_ids = tuple(sorted(case.source_chunk_ids))
    return source_ids if len(source_ids) > 1 else None


def _source_point(case_id: str, ordinal: int, record: SourceRecord) -> AnswerPoint:
    reference = _rule_reference(record)
    return AnswerPoint(
        point_id=f"{case_id}-evidence-{ordinal}",
        text=_atomic_source_claim(record.text),
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=[record.chunk_id],
        supporting_rules=[reference],
    )


def _comparison_point(
    case_id: str,
    ordinal: int,
    left: SourceRecord,
    right: SourceRecord,
) -> AnswerPoint:
    """Create one scoreable claim that requires both source passages to answer."""
    return AnswerPoint(
        point_id=f"{case_id}-comparison-{ordinal}",
        text=(
            f"Compare {left.ruleset.value.replace('_', ' ')} Rule {left.rule_number} "
            f"({_short_excerpt(_atomic_source_claim(left.text), 60)}) with "
            f"{right.ruleset.value.replace('_', ' ')} Rule {right.rule_number} "
            f"({_short_excerpt(_atomic_source_claim(right.text), 60)}). Explicitly distinguish "
            "the two evidenced requirements; do not infer an unstated priority."
        ),
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=[left.chunk_id, right.chunk_id],
        supporting_rules=[_rule_reference(left), _rule_reference(right)],
    )


def _atomic_source_claim(text: str) -> str:
    normalized = " ".join(text.split())
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if len(sentence.strip()) >= 24
    ]
    candidate = sentences[0] if sentences else normalized
    if len(candidate) <= 360:
        return candidate
    clauses = [
        clause.strip()
        for clause in re.split(r"(?<=[;:])\s+", candidate)
        if len(clause.strip()) >= 24
    ]
    complete_clause = next((clause for clause in clauses if len(clause) <= 360), None)
    return complete_clause or _short_excerpt(candidate, 360)


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


def _comparison_query(
    language: Language,
    left: SourceRecord,
    right: SourceRecord,
    ordinal: int,
) -> str:
    left_rule = f"{left.ruleset.value.replace('_', ' ')} Rule {left.rule_number}"
    right_rule = f"{right.ruleset.value.replace('_', ' ')} Rule {right.rule_number}"
    left_scenario = _scenario_label(left, ordinal)
    right_scenario = _scenario_label(right, ordinal)
    if language == Language.CHINESE:
        return (
            f"\u8bf7\u6bd4\u8f83 {left_rule} \u4e0e {right_rule} \u7684\u8bc1\u636e\u6bb5\u843d\uff1a"
            f"\u5206\u522b\u8bf4\u660e {_anchor(left)} \u548c {_anchor(right)} \u6240\u5bf9\u5e94\u7684\u53ef\u786e\u8ba4\u8981\u6c42\uff0c"
            "\u5e76\u660e\u786e\u533a\u5206\u4e24\u8005\uff0c\u4e0d\u8981\u63a8\u65ad\u8bc1\u636e\u672a\u8bf4\u660e\u7684\u4f18\u5148\u7ea7\u6216\u56e0\u679c\u5173\u7cfb\u3002"
            f" \u4ea4\u6613\u80cc\u666f\uff1a{left_scenario}\uff1b{right_scenario}\u3002"
        )
    return (
        f"Compare the evidence passages for {left_rule} and {right_rule}. State the requirement "
        f"evidenced by each passage concerning {_anchor(left)} and {_anchor(right)}, then explicitly "
        "distinguish those requirements without inferring an unstated legal priority or causal relationship. "
        f"Transaction contexts: {left_scenario}; {right_scenario}."
    )


def _follow_up_queries(
    language: Language,
    left: SourceRecord,
    right: SourceRecord,
    ordinal: int,
) -> Tuple[str, str]:
    left_rule = f"{left.ruleset.value.replace('_', ' ')} Rule {left.rule_number}"
    right_rule = f"{right.ruleset.value.replace('_', ' ')} Rule {right.rule_number}"
    if language == Language.CHINESE:
        return (
            f"\u5bf9\u4e8e {_scenario_label(left, ordinal)}\uff0c\u8bf7\u6839\u636e {left_rule} "
            "\u7684\u8bc1\u636e\u8bf4\u660e\u53ef\u786e\u8ba4\u7684\u8981\u6c42\u3002",
            "\u57fa\u4e8e\u4f60\u521a\u624d\u5bf9\u524d\u4e00\u6761\u8981\u6c42\u7684\u56de\u7b54\uff0c"
            f"\u8bf7\u5c06\u5176\u4e0e {right_rule} \u5bf9 {_scenario_label(right, ordinal)} "
            "\u7684\u8981\u6c42\u8fdb\u884c\u6bd4\u8f83\uff0c\u660e\u786e\u8bf4\u660e\u4e24\u8005\u7684\u533a\u522b\uff0c"
            "\u4e0d\u8981\u63a8\u65ad\u8bc1\u636e\u672a\u8bf4\u660e\u7684\u5173\u7cfb\u3002",
        )
    return (
        f"For the {_scenario_label(left, ordinal)}, what requirement is evidenced by {left_rule}?",
        "Based on your previous answer, compare that requirement with the requirement "
        f"evidenced by {right_rule} for the {_scenario_label(right, ordinal)}. Explicitly distinguish "
        "the two requirements without inferring an unstated legal relationship.",
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
        "transaction_type": transaction_type,
    }


def _format_size_test_inputs(inputs: Mapping[str, float | int | str]) -> str:
    fields = (
        ("market cap", "issuer_market_cap"),
        ("total assets", "issuer_total_assets"),
        ("net assets", "issuer_net_assets"),
        ("annual profit", "issuer_annual_profit"),
        ("shares outstanding", "issuer_shares_outstanding"),
        ("consideration", "transaction_consideration"),
        ("acquired assets", "acquired_assets"),
        ("acquired profit", "acquired_profit"),
        ("acquired net assets", "acquired_net_assets"),
        ("transaction type", "transaction_type"),
    )
    values = "; ".join(f"{label}: {inputs[key]}" for label, key in fields)
    return f"Size-test inputs (HK$ millions except shares): {values}."


def _pure_size_test_case(
    case_id: str,
    language: Language,
    difficulty: Difficulty,
    ordinal: int,
    registry: SourceRegistry,
    seed: int,
) -> BenchmarkCase:
    """Create a tool-only case whose gold evidence is the calculator output."""
    size_inputs = _tool_inputs(ordinal)
    size_output = SizeTestCalculatorTool().run(size_inputs)
    if "error" in size_output:
        raise RuntimeError(f"generated size-test inputs are invalid: {size_output}")

    if language == Language.CHINESE:
        query = (
            "\u8bf7\u6839\u636e\u4e0b\u5217\u6570\u503c\u8ba1\u7b97\u8be5\u4ea4\u6613\u7684\u89c4\u6a21\u6d4b\u8bd5\u7ed3\u679c\u3002 "
            + _format_size_test_inputs(size_inputs)
        )
    else:
        query = "Calculate the size-test result from the following inputs. " + _format_size_test_inputs(size_inputs)

    call = ExpectedToolCall(
        order=1,
        tool_name="size_test_calculator",
        inputs=size_inputs,
        expected_output=size_output,
        numeric_tolerances={"highest_ratio": 0.01},
    )
    point = AnswerPoint(
        point_id=f"{case_id}-size-result",
        text="The calculator returns the highest ratio and suggested classification for the supplied inputs.",
        evidence_kind=EvidenceKind.TOOL,
        supporting_tool_call_orders=[1],
    )
    return BenchmarkCase(
        case_id=case_id,
        case_type=CaseType.TOOL,
        query=query,
        language=language,
        primary_category=PrimaryCategory.SIZE_TEST_CALCULATION,
        capability_tags=_case_tags(language, "tool", "size_test", "tool_only"),
        difficulty=difficulty,
        as_of=registry.manifest.snapshot_date,
        expected_intent=ExpectedIntent.CALCULATION_REQUIRED,
        expected_route=RouteMode.TOOL_ONLY,
        answer_points=[point],
        expected_tool_calls=[call],
        provenance=_provenance(registry, seed),
    )


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
    query += " " + _format_size_test_inputs(size_inputs)
    query += f" Deal-specific commercial context: {_scenario_detail(record, ordinal)}."
    query += (
        f" Apply the regulatory consequence evidenced by {record.ruleset.value.replace('_', ' ')} "
        f"Rule {record.rule_number}."
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
        "is_connected": False,
    }
    if classifier_inputs["is_connected"]:
        classifier_inputs["connected_party_type"] = "director"
        if language == Language.CHINESE:
            query += " \u8fd9\u662f\u4e00\u9879\u6d89\u53ca\u8463\u4e8b\u7684\u5173\u8054\u4ea4\u6613\u3002"
        else:
            query += " This is a connected transaction involving a director."
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
    points.append(_source_point(case_id, len(points) + 1, record))
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
        and _is_canonical_rule_source(record)
    ]
    if not sources:
        raise ValueError("no eligible canonical Main Board/GEM rule-source records are available")
    return sorted(sources, key=lambda item: item.chunk_id)


def _notifiable_transaction_sources(registry: SourceRegistry) -> List[SourceRecord]:
    """Return canonical Rules chunks that can ground a Chapter 14/19 tool consequence."""
    keywords = (
        "notifiable transaction",
        "percentage ratio",
        "percentage ratios",
        "classification",
        "shareholder approval",
        "shareholders' approval",
        "circular",
        "announcement",
    )
    sources = []
    for record in _eligible_rule_sources(registry):
        prefix = "14." if record.ruleset == RuleSet.MAIN_BOARD else "19."
        if not (record.rule_number or "").startswith(prefix):
            continue
        text = normalize_text(record.text)
        if any(keyword in text for keyword in keywords):
            sources.append(record)
    if not sources:
        raise ValueError("no canonical transaction-classification sources are available")
    return sorted(sources, key=lambda item: item.chunk_id)


def _is_canonical_rule_source(record: SourceRecord) -> bool:
    """Exclude paragraph-numbered decisions and summary material from formal cases.

    The registry preserves a chunk's structural ``rule_number`` field for every
    document.  In review decisions that field is often a paragraph number, not
    an HKEX Listing Rule.  Formal benchmark questions may only name a rule when
    it comes from the canonical Rules documents and has a fully qualified
    number such as ``14.34`` or ``15A.22``.
    """
    filename = Path(record.source_path).name.casefold()
    rule_number = record.rule_number or ""
    text = normalize_text(record.text)
    starts_with_rule = bool(re.match(
        rf"^{re.escape(rule_number.casefold())}(?:\s|\(|[,:.\-])", text,
    ))
    return bool(
        filename in _CANONICAL_RULE_FILENAMES
        and _QUALIFIED_RULE_NUMBER_RE.fullmatch(rule_number)
        and starts_with_rule
    )


def _graph_pairs(
    edges: Iterable[Mapping[str, object]],
    records: Mapping[str, SourceRecord],
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
        if src in records and dst in records and src != dst and _pair_similarity(
            records[src], records[dst],
        ) < _MAX_COMPARISON_PAIR_SIMILARITY:
            pairs.add(tuple(sorted((src, dst))))
    if not pairs:
        raise ValueError("source graph does not contain connected eligible rule-source pairs")
    return sorted(pairs)


def _pair_similarity(left: SourceRecord, right: SourceRecord) -> float:
    left_tokens = set(normalize_text(left.text).split())
    right_tokens = set(normalize_text(right.text).split())
    if not left_tokens or not right_tokens:
        return 1.0
    overlap = len(left_tokens & right_tokens)
    # Jaccard alone makes a complete short rule appear dissimilar to the same
    # rule followed by a long appendix.  The containment score catches that
    # near-duplicate comparison pair as well.
    return max(
        overlap / len(left_tokens | right_tokens),
        overlap / min(len(left_tokens), len(right_tokens)),
    )


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


def _pick_ranked_source(
    values: Sequence[SourceRecord],
    key: str,
    ordinal: int,
) -> SourceRecord:
    if not values:
        raise ValueError(f"source pool is empty while generating {key}")
    ranked = sorted(
        values,
        key=lambda item: hashlib.sha256(f"{key}:{item.chunk_id}".encode("utf-8")).hexdigest(),
    )
    return ranked[ordinal % len(ranked)]


def _tool_source_for_classification(
    sources: Sequence[SourceRecord],
    classifier_output: Mapping[str, object],
    key: str,
    ordinal: int,
) -> SourceRecord:
    applicable_rules = {
        str(rule).strip().upper()
        for rule in classifier_output.get("applicable_rules", [])
        if str(rule).strip()
    }
    matching_sources = [
        record for record in sources
        if (record.rule_number or "").strip().upper() in applicable_rules
    ]
    if not matching_sources:
        raise ValueError(
            "no eligible source matches the classifier's applicable rules: "
            f"{sorted(applicable_rules)}"
        )
    return _pick_ranked_source(matching_sources, key, ordinal)


def generate_candidates(
    registry: SourceRegistry,
    graph_edges: Iterable[Mapping[str, object]],
    quota: SamplingQuota,
    target_multiplier: int = 2,
    seed: int = 42,
    case_id_prefix: str = "terra",
    excluded_multi_source_signatures: set[tuple[str, ...]] | None = None,
) -> List[BenchmarkCase]:
    if target_multiplier < 1:
        raise ValueError("target_multiplier must be at least 1")
    if registry.manifest is None:
        raise ValueError("candidate generation requires a source snapshot manifest")
    if not _slug(case_id_prefix):
        raise ValueError("case_id_prefix must contain at least one alphanumeric character")
    sources = _eligible_rule_sources(registry)
    source_by_id = {record.chunk_id: record for record in sources}
    needs_source_pairs = any(
        cell.primary_category in {
            PrimaryCategory.COMPARISON_MULTI_HOP,
            PrimaryCategory.MULTI_TURN_FOLLOW_UP,
        }
        for cell in quota.cells
    )
    pairs = _graph_pairs(graph_edges, source_by_id) if needs_source_pairs else []
    excluded_multi_source_signatures = excluded_multi_source_signatures or set()
    pairs = [
        pair for pair in pairs
        if tuple(sorted(pair)) not in excluded_multi_source_signatures
    ]
    if needs_source_pairs and not pairs:
        raise ValueError("no eligible source pairs remain after reference-release exclusions")
    generated: List[BenchmarkCase] = []
    used_sources: Dict[Tuple[str, str], set[str]] = defaultdict(set)
    used_pairs: set[Tuple[str, str]] = set()
    ordinal = 0

    for cell in sorted(quota.cells, key=lambda item: item.key):
        for index in range(cell.count * target_multiplier):
            ordinal += 1
            case_id = f"{_slug(case_id_prefix)}-{_slug(cell.primary_category.value)}-{cell.language.value}-{cell.difficulty.value}-{index + 1:03d}"
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
            if category == PrimaryCategory.SIZE_TEST_CALCULATION:
                generated.append(_pure_size_test_case(
                    case_id, cell.language, cell.difficulty, ordinal, registry, seed
                ))
                continue
            if category == PrimaryCategory.TOOL_CHAIN:
                size_inputs = _tool_inputs(ordinal)
                size_output = SizeTestCalculatorTool().run(size_inputs)
                classifier_output = TransactionClassifierTool().run({
                    "highest_ratio": size_output["highest_ratio"],
                    "transaction_type": size_inputs["transaction_type"],
                    "is_connected": False,
                })
                source = _tool_source_for_classification(
                    sources,
                    classifier_output,
                    f"{category.value}:{cell.language.value}",
                    index,
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
                        query=_comparison_query(cell.language, left, right, ordinal),
                        language=cell.language,
                        primary_category=category,
                        capability_tags=_case_tags(cell.language, "multi_hop", "connected_subgraph"),
                        difficulty=cell.difficulty,
                        as_of=registry.manifest.snapshot_date,
                        expected_intent=ExpectedIntent.COMPARISON,
                        expected_route=RouteMode.RETRIEVAL,
                        answer_points=[
                            _source_point(case_id, 1, left),
                            _source_point(case_id, 2, right),
                            _comparison_point(case_id, 3, left, right),
                        ],
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
                    first_query, second_query = _follow_up_queries(
                        cell.language, left, right, ordinal
                    )
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
                                answer_points=[_comparison_point(case_id, 2, left, right)],
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
                expected_route=(
                    RouteMode.TOOL_PLUS_RETRIEVAL
                    if category == PrimaryCategory.RULE_LOOKUP
                    else RouteMode.RETRIEVAL
                ),
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
    case_id_prefix: str = "terra",
    reference_benchmark_path: Path | None = None,
) -> CandidateGenerationManifest:
    registry = SourceRegistry.load(source_registry_path)
    graph_edges = read_jsonl(graph_edges_path)
    quota = SamplingQuota.model_validate(json.loads(Path(quota_path).read_text(encoding="utf-8")))
    excluded_signatures: set[tuple[str, ...]] = set()
    if reference_benchmark_path:
        for case in read_jsonl(reference_benchmark_path, BenchmarkCase):
            signature = _multi_source_signature(case)
            if signature:
                excluded_signatures.add(signature)
    candidates = generate_candidates(
        registry,
        graph_edges,
        quota,
        target_multiplier=target_multiplier,
        seed=seed,
        case_id_prefix=case_id_prefix,
        excluded_multi_source_signatures=excluded_signatures,
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
        excluded_reference_multi_source_count=len(excluded_signatures),
        category_counts=dict(Counter(case.primary_category.value for case in candidates)),
        language_counts=dict(Counter(case.language.value for case in candidates)),
        difficulty_counts=dict(Counter(case.difficulty.value for case in candidates)),
        candidates_sha256=sha256_file(output_path),
        created_at=datetime.now(tz=timezone.utc),
    )
    write_json(manifest_path, manifest)
    return manifest
