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
    ExpectedToolCall,
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
        expected_tools = _expected_tools(case)
        semantic_assessments = self._semantic_assessments(
            points,
            row,
            expected_tools,
        )
        assessment = [
            self._assess_point(
                point,
                row,
                semantic_assessments.get(point.point_id),
                expected_tools,
            )
            for point in points
        ]
        verification = row.verification_result or {}
        return GroundedAnswerAssessment(
            run_id=row.run_id,
            case_id=row.case_id,
            system=row.system,
            answer_hash=_answer_hash(row.answer),
            judge_backend=(
                "deterministic-diagnostic"
                if self.backend == "deterministic"
                else f"llm:{self.model}"
            ),
            rubric_version=(
                "r2-grounded-answer-diagnostic-v1"
                if self.backend == "deterministic"
                else "r2-grounded-answer-semantic-v2"
            ),
            point_assessments=assessment,
            unsupported_claims=list(verification.get("unsupported_claims", [])),
        )

    def _assess_point(
        self,
        point: AnswerPoint,
        row: EvaluationRunRow,
        semantic_assessment: Optional[Dict[str, Any]],
        expected_tools: List[ExpectedToolCall],
    ) -> GroundedAnswerPointAssessment:
        answered = (
            bool(semantic_assessment.get("answered"))
            if semantic_assessment is not None
            else _contains_answer_point(row.answer, point.text)
        )
        correct = (
            bool(semantic_assessment.get("correct"))
            and not bool(semantic_assessment.get("overstated"))
            if semantic_assessment is not None
            else answered
        )
        evidence_ids = _evidence_ids(row)
        tool_orders = _supported_tool_orders(row, expected_tools)
        source_support = sorted(set(point.supporting_chunk_ids) & evidence_ids)
        tool_support = sorted(set(point.supporting_tool_call_orders) & tool_orders)

        if point.evidence_kind == EvidenceKind.SOURCE:
            grounded = bool(source_support) and _semantic_supports_point(
                semantic_assessment,
            )
        elif point.evidence_kind == EvidenceKind.TOOL:
            grounded = bool(tool_support) and _semantic_supports_point(
                semantic_assessment,
            )
        else:
            grounded = _semantic_supports_point(semantic_assessment)

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
        row: EvaluationRunRow,
        expected_tools: List[ExpectedToolCall],
    ) -> Dict[str, Dict[str, Any]]:
        if self.backend == "deterministic":
            return {}
        if not points:
            return {}
        prompt = {
            "task": (
                "Assess each HKEX answer point independently. A point passes only "
                "when the answer covers it correctly, the supplied mapped source "
                "excerpt or tool output directly supports it, and the answer does "
                "not state an unsupported regulatory consequence as certain."
            ),
            "query": row.query,
            "answer": row.answer,
            "answer_points": [
                {
                    "point_id": point.point_id,
                    "text": point.text,
                    "evidence_kind": point.evidence_kind.value,
                    "mapped_evidence": _mapped_evidence_for_point(
                        point,
                        row,
                        expected_tools,
                    ),
                }
                for point in points
            ],
            "required_response": {
                "point_assessments": [
                    {
                        "point_id": "string",
                        "answered": True,
                        "correct": True,
                        "directly_supported": True,
                        "overstated": False,
                        "reason": "string",
                    }
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
                expected_ids = {point.point_id for point in points}
                point_ids = []
                decisions = {}
                for item in records:
                    if not isinstance(item, dict):
                        raise ValueError("point_assessments contains a non-object record")
                    if not {
                        "point_id",
                        "answered",
                        "correct",
                        "directly_supported",
                        "overstated",
                    }.issubset(item):
                        raise ValueError(
                            "point assessment is missing point_id, answered, correct, "
                            "directly_supported, or overstated"
                        )
                    point_id = str(item["point_id"])
                    point_ids.append(point_id)
                    decisions[point_id] = {
                        "answered": _as_boolean(item.get("answered")),
                        "correct": _as_boolean(item.get("correct")),
                        "directly_supported": _as_boolean(item.get("directly_supported")),
                        "overstated": _as_boolean(item.get("overstated")),
                        "reason": item.get("reason", ""),
                    }
                if len(point_ids) != len(set(point_ids)):
                    raise ValueError("point_assessments contains duplicate point_id values")
                received_ids = set(point_ids)
                if received_ids != expected_ids:
                    raise ValueError(
                        "point_assessments must decide every requested point exactly once; "
                        f"missing={sorted(expected_ids - received_ids)}, "
                        f"unexpected={sorted(received_ids - expected_ids)}"
                    )
                return decisions
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


def _expected_tools(case: BenchmarkCase) -> List[ExpectedToolCall]:
    return list(case.turns[-1].expected_tool_calls) if case.turns else list(case.expected_tool_calls)


def _semantic_supports_point(semantic_assessment: Optional[Dict[str, Any]]) -> bool:
    """Require a semantic direct-support decision in the formal LLM pathway."""
    if semantic_assessment is None:
        return True
    return bool(semantic_assessment.get("directly_supported"))


def _mapped_evidence_for_point(
    point: AnswerPoint,
    row: EvaluationRunRow,
    expected_tools: List[ExpectedToolCall],
) -> Dict[str, Any]:
    """Provide only the point's mapped source excerpts or tool facts to the judge."""
    if point.evidence_kind == EvidenceKind.SOURCE:
        source_ids = set(point.supporting_chunk_ids)
        excerpts = []
        for item in _source_evidence_records(row):
            chunk_id = item.get("chunk_id")
            if chunk_id in source_ids:
                excerpts.append(item)
        return {"source_excerpts": excerpts}
    if point.evidence_kind == EvidenceKind.TOOL:
        expected_by_order = {tool.order: tool for tool in expected_tools}
        calls_by_order = {
            index: call
            for index, call in enumerate(row.tool_calls, start=1)
            if isinstance(call, dict)
        }
        results_by_call_id = {
            result.get("call_id"): result
            for result in row.tool_results
            if isinstance(result, dict) and result.get("call_id")
        }
        tool_facts = []
        for order in point.supporting_tool_call_orders:
            expected = expected_by_order.get(order)
            call = calls_by_order.get(order)
            result = results_by_call_id.get((call or {}).get("call_id"))
            tool_facts.append({
                "order": order,
                "expected": expected.model_dump() if expected is not None else None,
                "actual_call": call,
                "actual_result": result,
            })
        return {"tool_facts": tool_facts}
    return {}


def _source_evidence_records(row: EvaluationRunRow) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for citation in row.citations:
        if not isinstance(citation, dict) or not citation.get("chunk_id"):
            continue
        chunk_id = str(citation["chunk_id"])
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        records.append({
            "chunk_id": chunk_id,
            "text": citation.get("snippet") or citation.get("text") or "",
        })
    selection = row.selected_evidence or {}
    for selected in selection.get("selected_chunks", []):
        if not isinstance(selected, dict) or not selected.get("chunk_id"):
            continue
        chunk_id = str(selected["chunk_id"])
        if chunk_id in seen_ids:
            continue
        seen_ids.add(chunk_id)
        chunk = selected.get("chunk") if isinstance(selected.get("chunk"), dict) else {}
        records.append({
            "chunk_id": chunk_id,
            "text": selected.get("text") or chunk.get("text") or "",
        })
    return records


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


def _supported_tool_orders(
    row: EvaluationRunRow,
    expected_tools: List[ExpectedToolCall],
) -> Set[int]:
    """Return tool orders with a successful result matching the frozen expectation."""
    expected_by_order = {tool.order: tool for tool in expected_tools}
    result_by_call_id = {
        result.get("call_id"): result
        for result in row.tool_results
        if isinstance(result, dict) and result.get("call_id")
    }
    supported_orders = set()
    for order, call in enumerate(row.tool_calls, start=1):
        if not isinstance(call, dict):
            continue
        expected = expected_by_order.get(order)
        result = result_by_call_id.get(call.get("call_id"))
        if (
            expected is not None
            and call.get("tool_name") == expected.tool_name
            and _tool_inputs_match(call.get("inputs"), expected.inputs)
            and result is not None
            and result.get("success")
            and _tool_output_matches(result.get("output"), expected)
        ):
            supported_orders.add(order)
    return supported_orders


def _tool_inputs_match(actual: Any, expected: Dict[str, Any]) -> bool:
    return isinstance(actual, dict) and all(actual.get(key) == value for key, value in expected.items())


def _tool_output_matches(actual: Any, expected: ExpectedToolCall) -> bool:
    if not expected.expected_output:
        return True
    if not isinstance(actual, dict):
        return False
    for key, expected_value in expected.expected_output.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            try:
                if abs(float(actual_value) - float(expected_value)) > expected.numeric_tolerances.get(key, 0.0):
                    return False
            except (TypeError, ValueError):
                return False
        elif actual_value != expected_value:
            return False
    return True


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
