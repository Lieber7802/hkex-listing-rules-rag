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
    ):
        self.model = model or settings.llm_model
        self._client = client

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
        response = self._get_client().chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Validate benchmark annotations against supplied evidence. Return strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.0,
        )
        raw = response.choices[0].message.content
        if not raw:
            raise ValueError("LLM judge returned an empty response")
        try:
            payload: Dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM judge returned invalid JSON: {exc}") from exc
        payload.update({
            "case_hash": case.content_hash(),
            "judge_model": self.model,
            "judge_prompt_hash": prompt_hash,
            "rubric_version": JUDGE_RUBRIC_VERSION,
        })
        return JudgeAssessment.model_validate(payload)
