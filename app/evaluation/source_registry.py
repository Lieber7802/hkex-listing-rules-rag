from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.schemas import (
    CorpusSnapshotManifest,
    RuleSet,
    SourceRecord,
    SourceStatus,
)
from app.schemas.document import Chunk


SOURCE_POLICY_VERSION = "1.0"
DEFAULT_MIN_TEXT_CHARS = 80

_WITHDRAWN_RE = re.compile(
    r"(?:^|\n)\s*(?:\[PAGE\s+\d+\]\s*)?withdrawn\s+(?:on|in|from|with\s+effect)\b"
    r"|\(\s*withdrawn\s+(?:on|in|from|with\s+effect)\b"
    r"|已撤回|撤回日期",
    re.IGNORECASE | re.MULTILINE,
)
_SUPERSEDED_RE = re.compile(
    r"(?:^|\n)\s*(?:\[PAGE\s+\d+\]\s*)?superseded\s+(?:on|in|from|by)\b"
    r"|\(\s*superseded\s+(?:on|in|from|by)\b"
    r"|已取代|被取代",
    re.IGNORECASE | re.MULTILINE,
)
_ARCHIVE_RE = re.compile(r"(?:^|/)archive(?:/|$)", re.IGNORECASE)
_ACTIVE_PATH_PARTS = (
    "/rules/",
    "/guidance/",
    "/enforcement_guidance/",
    "/forms_templates/",
    "/headline_categories/",
    "/review_committee_decisions/",
)


def normalize_source_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    return re.sub(r"/+", "/", normalized).lower()


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def infer_source_status(source_path: str, text: str) -> SourceStatus:
    path = normalize_source_path(source_path)
    if _WITHDRAWN_RE.search(text):
        return SourceStatus.WITHDRAWN
    if _SUPERSEDED_RE.search(text):
        return SourceStatus.SUPERSEDED
    if _ARCHIVE_RE.search(path):
        return SourceStatus.ARCHIVED
    if any(part in path for part in _ACTIVE_PATH_PARTS):
        return SourceStatus.ACTIVE
    return SourceStatus.UNKNOWN


def infer_ruleset(source_path: str, text: str = "") -> RuleSet:
    path = normalize_source_path(source_path)
    filename = Path(path).name
    if filename == "gem.pdf" or "/gem/" in path or filename.startswith("gem_"):
        return RuleSet.GEM
    if "main_board" in filename or "/main_board/" in path:
        return RuleSet.MAIN_BOARD
    if "/guidance/" in path or "guidance" in path:
        return RuleSet.GUIDANCE
    if re.search(r"\bmain board\b", text[:500], re.IGNORECASE):
        return RuleSet.MAIN_BOARD
    if re.search(r"\bgem\b", text[:500], re.IGNORECASE):
        return RuleSet.GEM
    return RuleSet.UNKNOWN


class SourceRegistry:
    def __init__(
        self,
        records: Iterable[SourceRecord],
        manifest: Optional[CorpusSnapshotManifest] = None,
    ):
        self.records = list(records)
        self.manifest = manifest
        self._by_chunk_id = {record.chunk_id: record for record in self.records}
        if len(self._by_chunk_id) != len(self.records):
            raise ValueError("source registry contains duplicate chunk_id values")

    @classmethod
    def load(cls, path: Path) -> "SourceRegistry":
        path = Path(path)
        manifest_path = path.parent / "snapshot_manifest.json"
        manifest = None
        if manifest_path.exists():
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = CorpusSnapshotManifest.model_validate(json.load(handle))
        return cls(read_jsonl(path, SourceRecord), manifest=manifest)

    def get(self, chunk_id: str) -> Optional[SourceRecord]:
        return self._by_chunk_id.get(chunk_id)

    def require(self, chunk_id: str) -> SourceRecord:
        record = self.get(chunk_id)
        if record is None:
            raise KeyError(f"unknown source chunk: {chunk_id}")
        return record

    def main_eligible(self, chunk_id: str) -> bool:
        record = self.get(chunk_id)
        return bool(record and record.eligible_main_benchmark)


def _chunk_payload(chunk: Any) -> Dict[str, Any]:
    if isinstance(chunk, Chunk):
        return chunk.model_dump()
    if hasattr(chunk, "model_dump"):
        return chunk.model_dump()
    return dict(chunk)


def _source_hash(chunks: List[Dict[str, Any]], source_path: Optional[Path]) -> str:
    if source_path and Path(source_path).is_file():
        return sha256_file(Path(source_path))
    serialized = json.dumps(chunks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(serialized)


def _status_priority(status: SourceStatus) -> int:
    return {
        SourceStatus.ACTIVE: 0,
        SourceStatus.UNKNOWN: 1,
        SourceStatus.ARCHIVED: 2,
        SourceStatus.SUPERSEDED: 3,
        SourceStatus.WITHDRAWN: 4,
    }[status]


def _document_status_priority(status: SourceStatus) -> int:
    return {
        SourceStatus.WITHDRAWN: 0,
        SourceStatus.SUPERSEDED: 1,
        SourceStatus.ARCHIVED: 2,
        SourceStatus.ACTIVE: 3,
        SourceStatus.UNKNOWN: 4,
    }[status]


def _parse_optional_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def build_source_registry(
    chunks: Iterable[Any],
    snapshot_date: date,
    source_path: Optional[Path] = None,
    metadata_overrides: Optional[Mapping[str, Mapping[str, Any]]] = None,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> Tuple[List[SourceRecord], CorpusSnapshotManifest, List[Dict[str, str]]]:
    payloads = [_chunk_payload(chunk) for chunk in chunks]
    overrides = metadata_overrides or {}
    provisional: List[Dict[str, Any]] = []

    inferred_by_source: Dict[str, List[SourceStatus]] = defaultdict(list)
    for payload in payloads:
        chunk_id = str(payload["chunk_id"])
        override = overrides.get(chunk_id, {})
        if "status" in override:
            continue
        source = str(payload.get("source_path", ""))
        text = str(payload.get("text", ""))
        inferred_by_source[normalize_source_path(source)].append(
            infer_source_status(source, text)
        )
    document_status = {
        source: min(statuses, key=_document_status_priority)
        for source, statuses in inferred_by_source.items()
    }

    for payload in payloads:
        chunk_id = str(payload["chunk_id"])
        override = dict(overrides.get(chunk_id, {}))
        text = str(payload.get("text", ""))
        source = str(payload.get("source_path", ""))
        status = SourceStatus(
            override.get(
                "status",
                document_status.get(
                    normalize_source_path(source),
                    infer_source_status(source, text),
                ),
            )
        )
        ruleset = RuleSet(override.get("ruleset", infer_ruleset(source, text)))
        effective_from = _parse_optional_date(override.get("effective_from"))
        effective_to = _parse_optional_date(override.get("effective_to"))
        normalized = normalize_text(text)

        provisional.append({
            "chunk_id": chunk_id,
            "document_id": str(payload.get("document_id", "")),
            "source_path": source,
            "text": text,
            "rule_number": payload.get("rule_number"),
            "chapter": payload.get("chapter"),
            "section_title": payload.get("section_title"),
            "ruleset": ruleset,
            "status": status,
            "snapshot_date": snapshot_date,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "content_hash": sha256_text(text),
            "canonical_text_hash": sha256_text(normalized),
        })

    by_hash: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in provisional:
        by_hash[item["canonical_text_hash"]].append(item)

    duplicate_map: List[Dict[str, str]] = []
    canonical_by_hash: Dict[str, str] = {}
    for text_hash, group in by_hash.items():
        canonical = min(
            group,
            key=lambda item: (
                _status_priority(item["status"]),
                normalize_source_path(item["source_path"]),
                item["chunk_id"],
            ),
        )
        canonical_by_hash[text_hash] = canonical["chunk_id"]
        if len(group) > 1:
            for item in group:
                if item["chunk_id"] != canonical["chunk_id"]:
                    duplicate_map.append({
                        "chunk_id": item["chunk_id"],
                        "canonical_chunk_id": canonical["chunk_id"],
                        "canonical_text_hash": text_hash,
                    })

    records: List[SourceRecord] = []
    for item in provisional:
        canonical_id = canonical_by_hash[item["canonical_text_hash"]]
        duplicate_of = canonical_id if canonical_id != item["chunk_id"] else None
        reasons: List[str] = []
        normalized_length = len(normalize_text(item["text"]))

        if item["status"] != SourceStatus.ACTIVE:
            reasons.append(f"source_status:{item['status'].value}")
        if duplicate_of:
            reasons.append("exact_duplicate")
        if normalized_length < min_text_chars:
            reasons.append("text_too_short")
        if item["effective_from"] and snapshot_date < item["effective_from"]:
            reasons.append("not_yet_effective")
        if item["effective_to"] and snapshot_date > item["effective_to"]:
            reasons.append("no_longer_effective")

        records.append(SourceRecord(
            **item,
            duplicate_of=duplicate_of,
            eligible_main_benchmark=not reasons,
            eligible_stress=normalized_length > 0,
            exclusion_reasons=reasons,
        ))

    source_digest = _source_hash(payloads, source_path)
    status_counts = Counter(record.status.value for record in records)
    ruleset_counts = Counter(record.ruleset.value for record in records)
    exclusion_counts = Counter(
        reason
        for record in records
        for reason in record.exclusion_reasons
    )
    duplicate_groups = sum(1 for group in by_hash.values() if len(group) > 1)
    chunks_in_duplicate_groups = sum(len(group) for group in by_hash.values() if len(group) > 1)

    manifest = CorpusSnapshotManifest(
        snapshot_id=f"snapshot-{snapshot_date.isoformat()}-{source_digest[:12]}",
        snapshot_date=snapshot_date,
        source_path=str(source_path) if source_path else "in_memory",
        source_sha256=source_digest,
        policy_version=SOURCE_POLICY_VERSION,
        total_chunks=len(records),
        main_eligible_chunks=sum(record.eligible_main_benchmark for record in records),
        excluded_chunks=sum(not record.eligible_main_benchmark for record in records),
        stress_eligible_chunks=sum(record.eligible_stress for record in records),
        duplicate_groups=duplicate_groups,
        chunks_in_duplicate_groups=chunks_in_duplicate_groups,
        status_counts=dict(status_counts),
        ruleset_counts=dict(ruleset_counts),
        exclusion_reason_counts=dict(exclusion_counts),
    )
    return records, manifest, duplicate_map


def build_source_registry_file(
    chunks_path: Path,
    output_dir: Path,
    snapshot_date: date,
    metadata_overrides: Optional[Mapping[str, Mapping[str, Any]]] = None,
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> CorpusSnapshotManifest:
    chunks_path = Path(chunks_path)
    with chunks_path.open("r", encoding="utf-8") as handle:
        chunks = json.load(handle)
    if not isinstance(chunks, list):
        raise ValueError("chunks input must be a JSON array")

    records, manifest, duplicate_map = build_source_registry(
        chunks,
        snapshot_date=snapshot_date,
        source_path=chunks_path,
        metadata_overrides=metadata_overrides,
        min_text_chars=min_text_chars,
    )
    output_dir = Path(output_dir)
    write_jsonl(output_dir / "sources.jsonl", records)
    write_jsonl(output_dir / "duplicate_map.jsonl", duplicate_map)
    write_json(output_dir / "snapshot_manifest.json", manifest)
    return manifest
