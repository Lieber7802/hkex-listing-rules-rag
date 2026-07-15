from __future__ import annotations

import json
import pickle
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from pydantic import Field

from app.evaluation.dataset_loader import write_json, write_jsonl
from app.evaluation.schemas import Language, RuleSet, SourceRecord, StrictModel
from app.evaluation.source_registry import (
    SourceRegistry,
    normalize_source_path,
    normalize_text,
    sha256_file,
)


SOURCE_GRAPH_POLICY_VERSION = "1.0"


SCENARIO_KEYWORDS: Mapping[str, Tuple[str, ...]] = {
    "connected_transaction": (
        "connected transaction",
        "connected person",
        "chapter 14a",
        "associate",
        "關連交易",
        "關聯交易",
        "關連人士",
    ),
    "notifiable_transaction": (
        "notifiable transaction",
        "chapter 14",
        "percentage ratio",
        "須予公布的交易",
        "百分比率",
    ),
    "major_transaction": (
        "major transaction",
        "very substantial acquisition",
        "very substantial disposal",
        "主要交易",
        "非常重大收購",
        "非常重大出售",
    ),
    "disclosure_obligation": (
        "announcement",
        "disclose",
        "disclosure",
        "circular",
        "公告",
        "披露",
        "通函",
    ),
    "shareholder_approval": (
        "shareholder approval",
        "independent shareholders",
        "general meeting",
        "vote",
        "股東批准",
        "獨立股東",
        "股東大會",
    ),
    "size_test": (
        "size test",
        "percentage ratio",
        "assets ratio",
        "consideration ratio",
        "百分比率",
        "資產比率",
        "代價比率",
    ),
    "listing_eligibility": (
        "listing applicant",
        "market capitalization",
        "profit test",
        "eligibility",
        "上市申請人",
        "市值",
        "盈利測試",
        "上市資格",
    ),
    "exemption": (
        "exemption",
        "waiver",
        "de minimis",
        "豁免",
        "最低豁免水平",
    ),
    "procedure_flow": (
        "procedure",
        "application",
        "submit",
        "process",
        "steps",
        "程序",
        "申請",
        "提交",
        "步驟",
    ),
}


class SourceGraphNode(StrictModel):
    node_id: str
    chunk_id: str
    document_id: str
    source_path: str
    doc_type: str
    ruleset: RuleSet
    rule_number: Optional[str] = None
    source_status: str
    snapshot_date: str
    canonical_text_hash: str
    duplicate_of: Optional[str] = None
    eligible_main_benchmark: bool
    chapter: Optional[str] = None
    section_title: Optional[str] = None
    language: Language
    text: str
    keywords: List[str] = Field(default_factory=list)
    scenarios: List[str] = Field(default_factory=list)


class SourceGraphEdge(StrictModel):
    src: str
    dst: str
    edge_type: str
    weight: float = Field(ge=0.0, le=1.0)
    reason: str
    evidence: List[str] = Field(default_factory=list)


class SourceGraphStats(StrictModel):
    policy_version: str = SOURCE_GRAPH_POLICY_VERSION
    source_snapshot_id: str
    source_snapshot_hash: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    edge_type_counts: Dict[str, int]
    scenario_counts: Dict[str, int]
    language_counts: Dict[str, int]
    ruleset_counts: Dict[str, int]
    semantic_edges_enabled: bool
    semantic_index_path: Optional[str] = None
    semantic_top_k: int = Field(ge=1)
    semantic_threshold: float = Field(ge=-1.0, le=1.0)
    nodes_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    edges_sha256: Optional[str] = Field(default=None, min_length=64, max_length=64)
    created_at: datetime


def infer_doc_type(source_path: str) -> str:
    path = normalize_source_path(source_path)
    if "/rules/" in path:
        return "rule"
    if "guidance_letters" in path:
        return "guidance_letter"
    if "listing_decisions" in path:
        return "listing_decision"
    if "/faqs/" in path:
        return "faq"
    if "review_committee_decisions" in path:
        return "review_decision"
    if "enforcement_guidance" in path:
        return "enforcement"
    if "forms_templates" in path:
        return "form_template"
    return "other"


def infer_language(text: str) -> Language:
    cjk_count = sum("\u4e00" <= char <= "\u9fff" for char in text)
    latin_count = sum(char.isascii() and char.isalpha() for char in text)
    if cjk_count and latin_count:
        return Language.MIXED if cjk_count >= 8 else Language.ENGLISH
    if cjk_count:
        return Language.CHINESE
    return Language.ENGLISH


def tag_scenarios(text: str) -> Tuple[List[str], List[str]]:
    normalized = normalize_text(text)
    scenarios: List[str] = []
    matched_keywords: Set[str] = set()
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        matches = [keyword for keyword in keywords if keyword.casefold() in normalized]
        if matches:
            scenarios.append(scenario)
            matched_keywords.update(matches)
    return sorted(scenarios), sorted(matched_keywords)


def _normalize_rule_number(value: str) -> str:
    value = value.upper().strip()
    value = re.sub(r"^(?:MAIN\s+BOARD|GEM)\s+", "", value)
    value = re.sub(r"^RULES?\s+", "", value)
    return value.strip(" .,:;()[]")


_RULE_REFERENCE_RE = re.compile(
    r"(?:(MAIN\s+BOARD|GEM)\s+)?RULES?\s+"
    r"([0-9]{1,2}[A-Z]?(?:\.[0-9A-Z]+)?)",
    re.IGNORECASE,
)
_CHINESE_RULE_REFERENCE_RE = re.compile(
    r"(?:上市規則|《上市規則》|規則|第)\s*"
    r"([0-9]{1,2}[A-Z]?(?:\.[0-9A-Z]+)?)\s*(?:條|章)?",
    re.IGNORECASE,
)


def extract_rule_references(text: str, source_ruleset: RuleSet) -> List[Tuple[RuleSet, str]]:
    references: Set[Tuple[RuleSet, str]] = set()
    for board, number in _RULE_REFERENCE_RE.findall(text):
        board_name = board.upper().replace(" ", "")
        if board_name == "MAINBOARD":
            ruleset = RuleSet.MAIN_BOARD
        elif board_name == "GEM":
            ruleset = RuleSet.GEM
        else:
            ruleset = source_ruleset
        if ruleset in {RuleSet.MAIN_BOARD, RuleSet.GEM}:
            references.add((ruleset, _normalize_rule_number(number)))
    if source_ruleset in {RuleSet.MAIN_BOARD, RuleSet.GEM}:
        for number in _CHINESE_RULE_REFERENCE_RE.findall(text):
            references.add((source_ruleset, _normalize_rule_number(number)))
    return sorted(references, key=lambda item: (item[0].value, item[1]))


def build_nodes(records: Iterable[SourceRecord]) -> List[SourceGraphNode]:
    nodes: List[SourceGraphNode] = []
    for record in sorted(records, key=lambda item: item.chunk_id):
        if not record.eligible_main_benchmark or record.duplicate_of is not None:
            continue
        scenarios, keywords = tag_scenarios(record.text)
        nodes.append(SourceGraphNode(
            node_id=f"chunk:{record.chunk_id}",
            chunk_id=record.chunk_id,
            document_id=record.document_id,
            source_path=record.source_path,
            doc_type=infer_doc_type(record.source_path),
            ruleset=record.ruleset,
            rule_number=record.rule_number,
            source_status=record.status.value,
            snapshot_date=record.snapshot_date.isoformat(),
            canonical_text_hash=record.canonical_text_hash,
            duplicate_of=record.duplicate_of,
            eligible_main_benchmark=record.eligible_main_benchmark,
            chapter=record.chapter,
            section_title=record.section_title,
            language=infer_language(record.text),
            text=record.text,
            keywords=keywords,
            scenarios=scenarios,
        ))
    return nodes


class _EdgeCollector:
    def __init__(self) -> None:
        self._edges: Dict[Tuple[str, str, str], SourceGraphEdge] = {}

    def add(
        self,
        left: str,
        right: str,
        edge_type: str,
        weight: float,
        reason: str,
        evidence: Sequence[str] = (),
    ) -> None:
        if left == right:
            return
        src, dst = sorted((left, right))
        key = (src, dst, edge_type)
        candidate = SourceGraphEdge(
            src=src,
            dst=dst,
            edge_type=edge_type,
            weight=round(float(weight), 6),
            reason=reason,
            evidence=sorted(set(evidence)),
        )
        current = self._edges.get(key)
        if current is None or candidate.weight > current.weight:
            self._edges[key] = candidate

    def values(self) -> List[SourceGraphEdge]:
        return [self._edges[key] for key in sorted(self._edges)]


def _connect_groups(
    groups: Mapping[str, Sequence[SourceGraphNode]],
    collector: _EdgeCollector,
    edge_type: str,
    weight: float,
    reason_prefix: str,
    neighbors: int = 2,
) -> None:
    for group_value, raw_nodes in sorted(groups.items()):
        nodes = sorted(raw_nodes, key=lambda item: item.chunk_id)
        for index, node in enumerate(nodes):
            for offset in range(1, min(neighbors, len(nodes) - index - 1) + 1):
                collector.add(
                    node.node_id,
                    nodes[index + offset].node_id,
                    edge_type,
                    weight,
                    f"{reason_prefix}: {group_value}",
                    [group_value],
                )


def _group_nodes(
    nodes: Sequence[SourceGraphNode],
    value_getter,
) -> Dict[str, List[SourceGraphNode]]:
    groups: Dict[str, List[SourceGraphNode]] = defaultdict(list)
    for node in nodes:
        for value in value_getter(node):
            if value:
                groups[str(value)].append(node)
    return groups


def _add_rule_reference_edges(
    nodes: Sequence[SourceGraphNode],
    collector: _EdgeCollector,
) -> None:
    by_rule: Dict[Tuple[RuleSet, str], List[SourceGraphNode]] = defaultdict(list)
    for node in nodes:
        if node.rule_number and node.ruleset in {RuleSet.MAIN_BOARD, RuleSet.GEM}:
            by_rule[(node.ruleset, _normalize_rule_number(node.rule_number))].append(node)
    for values in by_rule.values():
        values.sort(key=lambda item: item.chunk_id)

    for node in nodes:
        for ruleset, rule_number in extract_rule_references(node.text, node.ruleset):
            targets = by_rule.get((ruleset, rule_number), [])
            target = next((item for item in targets if item.chunk_id != node.chunk_id), None)
            if target is not None:
                collector.add(
                    node.node_id,
                    target.node_id,
                    "rule_reference",
                    0.95,
                    f"Source text explicitly references {ruleset.value} Rule {rule_number}",
                    [ruleset.value, rule_number],
                )


def _add_tool_dependency_edges(
    nodes: Sequence[SourceGraphNode],
    collector: _EdgeCollector,
) -> None:
    size_nodes = [node for node in nodes if "size_test" in node.scenarios]
    downstream = [
        node
        for node in nodes
        if set(node.scenarios) & {
            "notifiable_transaction",
            "major_transaction",
            "disclosure_obligation",
        }
    ]
    if not downstream:
        return
    downstream.sort(key=lambda item: item.chunk_id)
    for index, node in enumerate(sorted(size_nodes, key=lambda item: item.chunk_id)):
        target = downstream[index % len(downstream)]
        if target.chunk_id == node.chunk_id and len(downstream) > 1:
            target = downstream[(index + 1) % len(downstream)]
        collector.add(
            node.node_id,
            target.node_id,
            "tool_dependency",
            0.90,
            "Size-test evidence connects to transaction classification or disclosure evidence",
            ["size_test", "classification_or_disclosure"],
        )


def _add_semantic_edges(
    nodes: Sequence[SourceGraphNode],
    collector: _EdgeCollector,
    vector_index_path: Path,
    chunk_ids_path: Path,
    top_k: int,
    threshold: float,
    max_edges_per_node: int,
) -> None:
    import faiss
    import numpy as np

    index = faiss.read_index(str(vector_index_path))
    with Path(chunk_ids_path).open("rb") as handle:
        chunk_ids = pickle.load(handle)
    if index.ntotal != len(chunk_ids):
        raise ValueError(
            f"FAISS/vector ID count mismatch: index={index.ntotal}, IDs={len(chunk_ids)}"
        )
    source_positions = {chunk_id: position for position, chunk_id in enumerate(chunk_ids)}
    eligible_nodes = [node for node in nodes if node.chunk_id in source_positions]
    missing = sorted(node.chunk_id for node in nodes if node.chunk_id not in source_positions)
    if missing:
        raise ValueError(f"eligible source graph nodes are missing from FAISS: {missing[:10]}")
    positions = np.asarray([source_positions[node.chunk_id] for node in eligible_nodes], dtype=np.int64)
    vectors = np.vstack([index.reconstruct(int(position)) for position in positions]).astype(np.float32)
    faiss.normalize_L2(vectors)

    hnsw = faiss.IndexHNSWFlat(index.d, 32, faiss.METRIC_INNER_PRODUCT)
    faiss.omp_set_num_threads(1)
    hnsw.hnsw.efConstruction = 80
    hnsw.hnsw.efSearch = max(64, top_k * 4)
    hnsw.add(vectors)
    search_k = min(len(eligible_nodes), max(top_k + 1, max_edges_per_node + 1))

    batch_size = 256
    for start in range(0, len(eligible_nodes), batch_size):
        scores, indices = hnsw.search(vectors[start:start + batch_size], search_k)
        for local_index, (row_scores, row_indices) in enumerate(zip(scores, indices)):
            source_index = start + local_index
            source_node = eligible_nodes[source_index]
            kept = 0
            for score, target_index in zip(row_scores, row_indices):
                if target_index < 0 or int(target_index) == source_index:
                    continue
                if float(score) < threshold:
                    continue
                target_node = eligible_nodes[int(target_index)]
                collector.add(
                    source_node.node_id,
                    target_node.node_id,
                    "semantic_similarity",
                    min(0.85, max(0.60, float(score))),
                    "Existing normalized FAISS vectors exceed the semantic threshold",
                    [f"cosine={float(score):.6f}"],
                )
                kept += 1
                if kept >= max_edges_per_node:
                    break


def build_source_graph(
    registry: SourceRegistry,
    vector_index_path: Optional[Path] = None,
    chunk_ids_path: Optional[Path] = None,
    semantic_top_k: int = 10,
    semantic_threshold: float = 0.72,
    max_semantic_edges_per_node: int = 5,
) -> Tuple[List[SourceGraphNode], List[SourceGraphEdge], SourceGraphStats]:
    if registry.manifest is None:
        raise ValueError("source registry manifest is required for graph provenance")
    nodes = build_nodes(registry.records)
    collector = _EdgeCollector()

    same_rule = _group_nodes(
        nodes,
        lambda node: [
            f"{node.ruleset.value}:{_normalize_rule_number(node.rule_number)}"
        ] if node.rule_number else [],
    )
    _connect_groups(same_rule, collector, "same_rule", 1.0, "Same ruleset and rule number")

    same_section = _group_nodes(
        nodes,
        lambda node: [normalize_text(node.section_title)] if node.section_title else [],
    )
    _connect_groups(same_section, collector, "same_section", 0.55, "Same section title", 1)

    same_chapter = _group_nodes(
        nodes,
        lambda node: [f"{node.ruleset.value}:{node.chapter}"] if node.chapter else [],
    )
    _connect_groups(same_chapter, collector, "same_chapter", 0.40, "Same ruleset and chapter", 1)

    scenarios = _group_nodes(nodes, lambda node: node.scenarios)
    _connect_groups(scenarios, collector, "same_scenario", 0.70, "Shared domain scenario", 2)

    keywords = _group_nodes(nodes, lambda node: node.keywords)
    _connect_groups(keywords, collector, "keyword_overlap", 0.50, "Shared domain keyword", 1)

    _add_rule_reference_edges(nodes, collector)
    _add_tool_dependency_edges(nodes, collector)

    semantic_enabled = bool(vector_index_path and chunk_ids_path)
    if semantic_enabled:
        _add_semantic_edges(
            nodes,
            collector,
            Path(vector_index_path),
            Path(chunk_ids_path),
            semantic_top_k,
            semantic_threshold,
            max_semantic_edges_per_node,
        )

    edges = collector.values()
    stats = SourceGraphStats(
        source_snapshot_id=registry.manifest.snapshot_id,
        source_snapshot_hash=registry.manifest.source_sha256,
        node_count=len(nodes),
        edge_count=len(edges),
        edge_type_counts=dict(Counter(edge.edge_type for edge in edges)),
        scenario_counts=dict(Counter(scenario for node in nodes for scenario in node.scenarios)),
        language_counts=dict(Counter(node.language.value for node in nodes)),
        ruleset_counts=dict(Counter(node.ruleset.value for node in nodes)),
        semantic_edges_enabled=semantic_enabled,
        semantic_index_path=str(vector_index_path) if vector_index_path else None,
        semantic_top_k=semantic_top_k,
        semantic_threshold=semantic_threshold,
        created_at=datetime.now(tz=timezone.utc),
    )
    return nodes, edges, stats


def build_source_graph_files(
    source_registry_path: Path,
    output_dir: Path,
    vector_index_path: Optional[Path] = None,
    chunk_ids_path: Optional[Path] = None,
    semantic_top_k: int = 10,
    semantic_threshold: float = 0.72,
    max_semantic_edges_per_node: int = 5,
) -> SourceGraphStats:
    registry = SourceRegistry.load(source_registry_path)
    nodes, edges, stats = build_source_graph(
        registry,
        vector_index_path=vector_index_path,
        chunk_ids_path=chunk_ids_path,
        semantic_top_k=semantic_top_k,
        semantic_threshold=semantic_threshold,
        max_semantic_edges_per_node=max_semantic_edges_per_node,
    )
    output_dir = Path(output_dir)
    nodes_path = output_dir / "nodes.jsonl"
    edges_path = output_dir / "edges.jsonl"
    write_jsonl(nodes_path, nodes)
    write_jsonl(edges_path, edges)
    stats = stats.model_copy(update={
        "nodes_sha256": sha256_file(nodes_path),
        "edges_sha256": sha256_file(edges_path),
    })
    write_json(output_dir / "graph_stats.json", stats)
    return stats
