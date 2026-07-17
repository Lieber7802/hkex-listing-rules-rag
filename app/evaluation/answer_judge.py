from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional, Set

from app.agents.coverage_checker import _tokenize_mixed
from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    EvidenceKind,
    EvaluationRunRow,
    GroundedAnswerAssessment,
    GroundedAnswerPointAssessment,
)


class GroundedAnswerJudge:
    """Judge answer points against the frozen evidence mapping for a run row."""

    def __init__(
        self,
        backend: str = "deterministic",
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_attempts: int = 3,
    ) -> None:
        if backend not in {"deterministic", "llm"}:
            raise ValueError(f"unsupported grounded answer judge backend: {backend}")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.backend = backend
        self.model = model or settings.llm_model
        self._client = client
        self.max_attempts = max_attempts

    def assess(
        self,
        case: BenchmarkCase,
        row: EvaluationRunRow,
    ) -> GroundedAnswerAssessment:
        points = _expected_points(case)
        semantic_assessments = self._semantic_assessments(points, row.answer)
        assessment = [
            self._assess_point(point, row, semantic_assessments.get(point.point_id))
            for point in points
        ]
        verification = row.verification_result or {}
        return GroundedAnswerAssessment(
            run_id=row.run_id,
            case_id=row.case_id,
            system=row.system,
            answer_hash=_answer_hash(row.answer),
            judge_backend=(self.backend if self.backend == "deterministic" else f"llm:{self.model}"),
            point_assessments=assessment,
            unsupported_claims=list(verification.get("unsupported_claims", [])),
        )

    def _assess_point(
        self,
        point: AnswerPoint,
        row: EvaluationRunRow,
        semantic_assessment: Optional[Dict[str, Any]],
    ) -> GroundedAnswerPointAssessment:
        answered = (
            bool(semantic_assessment.get("answered"))
            if semantic_assessment is not None
            else _contains_answer_point(row.answer, point.text)
        )
        correct = (
            bool(semantic_assessment.get("correct"))
            if semantic_assessment is not None
            else answered
        )
        evidence_ids = _evidence_ids(row)
        tool_orders = _successful_tool_orders(row)
        source_support = sorted(set(point.supporting_chunk_ids) & evidence_ids)
        tool_support = sorted(set(point.supporting_tool_call_orders) & tool_orders)

        if point.evidence_kind == EvidenceKind.SOURCE:
            grounded = bool(source_support)
        elif point.evidence_kind == EvidenceKind.TOOL:
            grounded = bool(tool_support)
        else:
            grounded = True

        return GroundedAnswerPointAssessment(
            point_id=point.point_id,
            answered=answered,
            correct=correct,
            grounded=grounded,
            supporting_chunk_ids=source_support,
            supporting_tool_call_orders=tool_support,
            reason=(
                str(semantic_assessment.get("reason"))
                if semantic_assessment is not None and semantic_assessment.get("reason")
                else _reason(answered, grounded, point.evidence_kind)
            ),
        )

    def _semantic_assessments(
        self,
        points: List[AnswerPoint],
        answer: str,
    ) -> Dict[str, Dict[str, Any]]:
        if self.backend == "deterministic":
            return {}
        prompt = {
            "task": (
                "Assess whether the answer covers each HKEX answer point correctly. "
                "Do not assess source grounding; it is checked separately."
            ),
            "answer": answer,
            "answer_points": [
                {"point_id": point.point_id, "text": point.text}
                for point in points
            ],
            "required_response": {
                "point_assessments": [
                    {"point_id": "string", "answered": True, "correct": True, "reason": "string"}
                ]
            },
        }
        errors = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return one strict JSON object and no prose.",
                        },
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                    temperature=0.0,
                    max_tokens=1000,
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
                records = payload.get("point_assessments", [])
                if not isinstance(records, list):
                    raise ValueError("point_assessments is not a list")
                return {
                    str(item["point_id"]): {
                        "answered": _as_boolean(item.get("answered")),
                        "correct": _as_boolean(item.get("correct")),
                        "reason": item.get("reason", ""),
                    }
                    for item in records
                    if isinstance(item, dict) and item.get("point_id")
                }
            except Exception as exc:
                errors.append(f"attempt {attempt}: {exc}")
        raise ValueError(
            f"LLM grounded answer judge failed after {self.max_attempts} attempts: {errors[-1]}"
        )

    def _get_client(self) -> Any:
        client = self._client if self._client is not None else get_llm_client()
        if client is None:
            raise RuntimeError("LLM grounded answer judge is unavailable")
        return client


def assess_rows(
    cases: Iterable[BenchmarkCase],
    rows: Iterable[EvaluationRunRow],
    backend: str = "deterministic",
    model: Optional[str] = None,
    client: Optional[Any] = None,
) -> List[GroundedAnswerAssessment]:
    case_map = {case.case_id: case for case in cases}
    judge = GroundedAnswerJudge(backend=backend, model=model, client=client)
    return [
        judge.assess(case_map[row.case_id], row)
        for row in rows
        if row.row_type.value in {"single_turn", "aggregate"} and row.case_id in case_map
    ]


def _expected_points(case: BenchmarkCase) -> List[AnswerPoint]:
    return list(case.turns[-1].answer_points) if case.turns else list(case.answer_points)


def _answer_hash(answer: str) -> str:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()


def _contains_answer_point(answer: str, point_text: str) -> bool:
    expected_tokens = _tokenize_mixed(point_text.lower())
    answer_tokens = _tokenize_mixed(answer.lower())
    if not expected_tokens:
        return point_text.lower() in answer.lower()
    return len(expected_tokens & answer_tokens) / len(expected_tokens) >= 0.6


def _evidence_ids(row: EvaluationRunRow) -> Set[str]:
    ids = {
        item.get("chunk_id")
        for item in row.citations
        if isinstance(item, dict) and item.get("chunk_id")
    }
    selection = row.selected_evidence or {}
    ids.update(
        item.get("chunk_id")
        for item in selection.get("selected_chunks", [])
        if isinstance(item, dict) and item.get("chunk_id")
    )
    return ids


def _successful_tool_orders(row: EvaluationRunRow) -> Set[int]:
    successful_call_ids = {
        item.get("call_id")
        for item in row.tool_results
        if isinstance(item, dict) and item.get("success") and item.get("call_id")
    }
    return {
        index
        for index, call in enumerate(row.tool_calls, start=1)
        if isinstance(call, dict) and call.get("call_id") in successful_call_ids
    }


def _reason(answered: bool, grounded: bool, evidence_kind: EvidenceKind) -> str:
    if not answered:
        return "The answer does not cover the required answer point."
    if not grounded:
        return f"The answer point is not supported by mapped {evidence_kind.value} evidence."
    return "The answer point is covered and supported by mapped evidence."


def _json_payload_from_message(message: Any) -> Optional[str]:
    for raw in (getattr(message, "content", None), getattr(message, "reasoning_content", None)):
        if not isinstance(raw, str) or not raw.strip():
            continue
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
        if content.startswith("{"):
            return content
    return None


def _as_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 4
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "pass", "supported", "4", "5"}
    return False
