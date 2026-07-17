from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.evaluation.benchmark_validator import JUDGE_RUBRIC_VERSION, JUDGE_SCORE_RUBRIC
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment
from app.evaluation.source_registry import SourceRegistry


def build_judge_prompt(
    case: BenchmarkCase,
    source_registry: SourceRegistry,
) -> Tuple[str, str]:
    sources = []
    for chunk_id in case.source_chunk_ids:
        record = source_registry.get(chunk_id)
        if record is None:
            continue
        sources.append({
            "chunk_id": record.chunk_id,
            "ruleset": record.ruleset.value,
            "rule_number": record.rule_number,
            "source_path": record.source_path,
            "text": record.text[:1600],
        })

    case_payload = case.model_dump(mode="json")
    prompt = (
        "You are validating a source-grounded HKEX benchmark candidate, not answering "
        "the user query. Evaluate only the supplied case annotation against the supplied "
        "sources. Do not use unstated legal knowledge. Return one JSON object and no prose.\n\n"
        f"Rubric version: {JUDGE_RUBRIC_VERSION}\n"
        f"Rubric: {json.dumps(JUDGE_SCORE_RUBRIC, ensure_ascii=False, sort_keys=True)}\n\n"
        "Use null for source_support, expected_rules_valid, or answer_points_grounded "
        "only when that dimension is genuinely not applicable to the case type. "
        "Every required answer point must have one answer_point_results entry.\n\n"
        "Required JSON keys:\n"
        "source_support, expected_rules_valid, answer_points_grounded, category_fit, "
        "difficulty_fit, language_correct, no_unsupported_claims, answer_point_results, "
        "issues, judge_reason\n\n"
        f"Candidate:\n{json.dumps(case_payload, ensure_ascii=False, sort_keys=True)}\n\n"
        f"Sources:\n{json.dumps(sources, ensure_ascii=False, sort_keys=True)}"
    )
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return prompt, prompt_hash


class LLMBenchmarkJudge:
    def __init__(
        self,
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_attempts: int = 3,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.model = model or settings.llm_model
        self._client = client
        self.max_attempts = max_attempts

    def _get_client(self) -> Any:
        client = self._client if self._client is not None else get_llm_client()
        if client is None:
            raise RuntimeError("LLM judge is unavailable: shared LLM client is not configured")
        return client

    def assess(
        self,
        case: BenchmarkCase,
        source_registry: SourceRegistry,
    ) -> JudgeAssessment:
        if self.model == case.provenance.generator_model:
            raise ValueError("judge model must differ from the benchmark generator model")
        prompt, prompt_hash = build_judge_prompt(case, source_registry)
        errors = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Validate benchmark annotations against supplied evidence. Return strict JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1800,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                errors.append(f"attempt {attempt}: API call failed: {exc}")
                continue
            raw = _json_payload_from_message(response.choices[0].message)
            if not raw:
                errors.append(f"attempt {attempt}: no JSON object in model response")
                continue
            try:
                payload, _ = json.JSONDecoder().raw_decode(raw)
                if not isinstance(payload, dict):
                    raise ValueError("judge response is not a JSON object")
                payload = _normalize_response_payload(payload, case)
                payload.update({
                    "case_hash": case.content_hash(),
                    "judge_model": self.model,
                    "judge_prompt_hash": prompt_hash,
                    "rubric_version": JUDGE_RUBRIC_VERSION,
                })
                return JudgeAssessment.model_validate(payload)
            except Exception as exc:
                errors.append(f"attempt {attempt}: {exc}")
        raise ValueError(
            f"LLM judge did not produce a valid assessment after {self.max_attempts} attempts: "
            f"{errors[-1]}"
        )


def _extract_json_payload(raw: str) -> str:
    content = raw.strip()
    if "</think>" in content:
        content = content.split("</think>")[-1].strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()
    if not content.startswith("{"):
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            content = content[start:end + 1]
    return content


def _json_payload_from_message(message: Any) -> Optional[str]:
    for raw in (getattr(message, "content", None), getattr(message, "reasoning_content", None)):
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = _extract_json_payload(raw)
        if candidate.startswith("{"):
            return candidate
    return None


def _normalize_response_payload(
    payload: Dict[str, Any],
    case: BenchmarkCase,
) -> Dict[str, Any]:
    normalized = dict(payload)
    for key in ("language_correct", "no_unsupported_claims"):
        normalized[key] = _as_boolean(normalized.get(key))

    points = {
        point.point_id: point
        for point in [*case.answer_points, *(point for turn in case.turns for point in turn.answer_points)]
    }
    results = []
    for raw_result in normalized.get("answer_point_results", []):
        result = dict(raw_result)
        if "supported" not in result:
            support_value = next((
                result[key]
                for key in ("evaluation", "support", "score", "rating", "grounded")
                if key in result
            ), False)
            result["supported"] = _as_boolean(support_value)
        else:
            result["supported"] = _as_boolean(result["supported"])
        point = points.get(result.get("point_id"))
        if result["supported"] and point and point.supporting_chunk_ids and not result.get("supporting_chunk_ids"):
            result["supporting_chunk_ids"] = list(point.supporting_chunk_ids)
        results.append({
            "point_id": result.get("point_id"),
            "supported": result["supported"],
            "supporting_chunk_ids": result.get("supporting_chunk_ids", []),
            "reason": result.get("reason") or result.get("notes") or "No judge rationale was supplied.",
        })
    normalized["answer_point_results"] = results
    return normalized


def _as_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 4
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "pass", "supported", "5", "4"}
    return False
