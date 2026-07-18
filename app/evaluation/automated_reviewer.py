from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional, Tuple

from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.evaluation.benchmark_judge import _json_payload_from_message
from app.evaluation.schemas import AutomatedReview, ReviewStatus


AUTOMATED_REVIEW_PROTOCOL = "r2-automated-audit-v1"


def build_automated_review_prompt(packet: Mapping[str, Any]) -> Tuple[str, str]:
    """Build a self-contained prompt from the immutable review packet."""
    template = packet.get("review_template") or {}
    declared_dimensions = template.get("verified_dimensions") or []
    declared_chunks = template.get("verified_chunk_ids") or []
    primary_category = packet.get("primary_category") or packet.get("category")
    prompt_payload = {
        "case_id": packet.get("case_id"),
        "case_hash": packet.get("case_hash"),
        "primary_category": primary_category,
        "query": packet.get("query"),
        "turns": packet.get("turns") or [],
        "expected_rules": packet.get("expected_rules") or [],
        "answer_points": packet.get("answer_points") or [],
        "expected_tool_calls": packet.get("expected_tool_calls") or [],
        "negative_expectation": packet.get("negative_expectation"),
        "sources": packet.get("sources") or [],
        "independent_judge_result": packet.get("judge_assessment"),
        "required_dimensions": declared_dimensions,
        "declared_chunk_ids": declared_chunks,
    }
    prompt = (
        "You are an automated agent assessment for a frozen HKEX benchmark. You are not "
        "a human reviewer and must not claim legal expertise. Inspect only the supplied "
        "annotation, source excerpts, and independent judge result; do not add external legal knowledge. Return one "
        "JSON object and no prose.\n\n"
        "Approve only when every required review dimension is supported. For source-backed "
        "cases, verify that each answer point and declared rule is supported by its declared "
        "source chunk. For tool-only cases, verify the expected deterministic tool behavior. "
        "For negative_insufficient cases, verify that the specified refusal, clarification, "
        "or premise correction is the appropriate bounded behavior. Also check that the "
        "language and difficulty labels are not plainly inconsistent with the query and "
        "case structure, and that the independent judge result is not contradicted by the "
        "supplied evidence. In particular, an "
        "out-of-scope question must not be answered from the HKEX corpus, and a nonexistent "
        "rule must not be invented. The language label applies to the user query and conversation "
        "turns. Frozen source excerpts and structured answer points may remain in their original "
        "source language, so English evidence for a Chinese query is not by itself a language-label defect.\n\n"
        "Return exactly these keys:\n"
        "- status: APPROVED or REJECTED\n"
        "- verified_dimensions: an array drawn only from required_dimensions\n"
        "- verified_chunk_ids: an array drawn only from declared_chunk_ids\n"
        "- notes: a concise factual reason, including the defect when rejected\n\n"
        f"Review packet:\n{json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True)}"
    )
    return prompt, hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class LLMAutomatedReviewer:
    """Bounded structured reviewer for the explicitly automated-only release path."""

    def __init__(
        self,
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_attempts: int = 5,
        reviewer_id: str = "llm-automated-audit",
        reviewer_kind: str = "llm_subagent",
        review_protocol: str = AUTOMATED_REVIEW_PROTOCOL,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.model = model or settings.llm_model
        self._client = client
        self.max_attempts = max_attempts
        self.reviewer_id = reviewer_id
        self.reviewer_kind = reviewer_kind
        self.review_protocol = review_protocol

    def _get_client(self) -> Any:
        client = self._client if self._client is not None else get_llm_client()
        if client is None:
            raise RuntimeError("automated reviewer is unavailable: shared LLM client is not configured")
        return client

    def review(self, packet: Mapping[str, Any]) -> AutomatedReview:
        case_hash = packet.get("case_hash")
        if not isinstance(case_hash, str):
            raise ValueError("review packet requires case_hash")
        prompt, prompt_hash = build_automated_review_prompt(packet)
        errors = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Act as an automated benchmark auditor. Return strict JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    # Some Chinese and tool cases need enough room to return all declared
                    # dimensions plus a precise rejection note as valid JSON.
                    max_tokens=1200,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                raw = _json_payload_from_message(response.choices[0].message)
                if not raw:
                    raise ValueError("no JSON object in model response")
                payload, _ = json.JSONDecoder().raw_decode(raw)
                if not isinstance(payload, dict):
                    raise ValueError("review response is not a JSON object")
                return self._build_review(packet, payload, prompt_hash)
            except Exception as exc:
                errors.append(f"attempt {attempt}: {exc}")
        raise ValueError(
            "automated reviewer did not produce a valid review after "
            f"{self.max_attempts} attempts: {errors[-1]}"
        )

    def _build_review(
        self,
        packet: Mapping[str, Any],
        payload: Mapping[str, Any],
        prompt_hash: str,
    ) -> AutomatedReview:
        template = packet.get("review_template") or {}
        declared_dimensions = set(template.get("verified_dimensions") or [])
        declared_chunks = set(template.get("verified_chunk_ids") or [])
        status = _normalize_status(payload.get("status", payload.get("decision")))
        dimensions = _normalize_subset(
            payload.get("verified_dimensions"), declared_dimensions, "verified_dimensions"
        )
        chunks = _normalize_subset(
            payload.get("verified_chunk_ids"), declared_chunks, "verified_chunk_ids"
        )
        if status == ReviewStatus.APPROVED and set(dimensions) != declared_dimensions:
            raise ValueError("approved automated review must verify every required dimension")
        if status == ReviewStatus.APPROVED and declared_chunks and not chunks:
            raise ValueError("approved source-backed review must identify declared source chunks")
        notes = payload.get("notes")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError("automated review requires non-empty notes")
        return AutomatedReview(
            case_hash=packet["case_hash"],
            reviewer_id=self.reviewer_id,
            reviewer_kind=self.reviewer_kind,
            review_protocol=self.review_protocol,
            review_model=self.model,
            review_prompt_hash=prompt_hash,
            status=status,
            verified_dimensions=dimensions,
            verified_chunk_ids=chunks,
            notes=notes.strip(),
        )


def _normalize_status(value: Any) -> ReviewStatus:
    normalized = str(value or "").strip().lower()
    aliases = {
        "approved": ReviewStatus.APPROVED,
        "approve": ReviewStatus.APPROVED,
        "pass": ReviewStatus.APPROVED,
        "rejected": ReviewStatus.REJECTED,
        "reject": ReviewStatus.REJECTED,
        "fail": ReviewStatus.REJECTED,
    }
    if normalized not in aliases:
        raise ValueError("automated review status must be APPROVED or REJECTED")
    return aliases[normalized]


def _normalize_subset(value: Any, declared: set[str], field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a JSON string array")
    normalized = list(dict.fromkeys(value))
    unexpected = sorted(set(normalized) - declared)
    if unexpected:
        raise ValueError(f"{field_name} contains undeclared values: {unexpected}")
    return normalized
