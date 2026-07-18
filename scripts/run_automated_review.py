"""Run an explicitly non-human, structured audit over a frozen review packet."""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.automated_reviewer import (
    AUTOMATED_REVIEW_PROTOCOL,
    LLMAutomatedReviewer,
    build_automated_review_prompt,
)
from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.schemas import AutomatedReview, BenchmarkCase, JudgeAssessment, ReviewStatus
from app.evaluation.source_registry import sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--judge-assessments", type=Path, required=True)
    parser.add_argument("--primary-category", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reviewer-id", default="llm-automated-audit")
    parser.add_argument("--reviewer-kind", default="automated_agent_assessment")
    parser.add_argument("--review-protocol", default=AUTOMATED_REVIEW_PROTOCOL)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-manifest", type=Path)
    return parser.parse_args()


def _load_existing(path: Path, packet_by_case_id: dict[str, dict]) -> dict[str, dict]:
    if not path.exists():
        return {}
    records = {}
    for record in read_jsonl(path):
        case_id = record.get("case_id")
        review_payload = record.get("automated_review")
        if not isinstance(case_id, str) or not isinstance(review_payload, dict):
            continue
        try:
            review = AutomatedReview.model_validate(review_payload)
        except Exception:
            continue
        if review.status == ReviewStatus.PENDING:
            continue
        packet = packet_by_case_id.get(case_id)
        if (
            packet
            and review.status != ReviewStatus.PENDING
            and review.case_hash == packet.get("case_hash")
        ):
            records[case_id] = {
                "case_id": case_id,
                "automated_review": review.model_dump(mode="json"),
            }
    return records


def _load_judgements(path: Path) -> dict[str, JudgeAssessment]:
    records = read_jsonl(path)
    judgements = {
        record["case_id"]: JudgeAssessment.model_validate(record["assessment"])
        for record in records
    }
    if len(judgements) != len(records):
        raise ValueError("judge assessments contain duplicate case IDs")
    return judgements


def _pending_record(packet: dict, args: argparse.Namespace, error: Exception) -> dict:
    _, prompt_hash = build_automated_review_prompt(packet)
    review = AutomatedReview(
        case_hash=packet["case_hash"],
        reviewer_id=args.reviewer_id,
        reviewer_kind=args.reviewer_kind,
        review_protocol=args.review_protocol,
        review_model=args.model,
        review_prompt_hash=prompt_hash,
        status=ReviewStatus.PENDING,
        notes=f"Automated audit could not complete: {error}",
    )
    return {"case_id": packet["case_id"], "automated_review": review.model_dump(mode="json")}


def main() -> None:
    args = parse_args()
    if args.workers < 1:
        raise ValueError("workers must be at least 1")
    if args.max_attempts < 1:
        raise ValueError("max-attempts must be at least 1")
    raw_packet = read_jsonl(args.review_packet)
    raw_packet_by_case_id = {record.get("case_id"): record for record in raw_packet}
    if len(raw_packet_by_case_id) != len(raw_packet) or not all(isinstance(key, str) for key in raw_packet_by_case_id):
        raise ValueError("review packet must contain one unique string case_id per record")
    candidate_rows = read_jsonl(args.candidates, BenchmarkCase)
    candidates = {case.case_id: case for case in candidate_rows}
    if len(candidates) != len(candidate_rows):
        raise ValueError("candidates contain duplicate case IDs")
    judgements = _load_judgements(args.judge_assessments)
    allowed_categories = set(args.primary_category)
    packet_by_case_id = {}
    for case_id, raw_record in raw_packet_by_case_id.items():
        case = candidates.get(case_id)
        if case is None:
            raise ValueError(f"review packet case is absent from candidates: {case_id}")
        if raw_record.get("case_hash") != case.content_hash():
            raise ValueError(f"review packet hash mismatch for {case_id}")
        if raw_record.get("category") != case.primary_category.value:
            raise ValueError(f"review packet category mismatch for {case_id}")
        if case.primary_category.value not in allowed_categories:
            continue
        judgement = judgements.get(case_id)
        if judgement is None or judgement.case_hash != case.content_hash():
            raise ValueError(f"judge assessment is missing or mismatched for {case_id}")
        record = dict(raw_record)
        record["primary_category"] = case.primary_category.value
        record["judge_assessment"] = judgement.model_dump(mode="json")
        template = dict(record.get("review_template") or {})
        template["verified_dimensions"] = [
            "source_support",
            "rule_references",
            "language_label",
            "difficulty_label",
            "judge_consistency",
        ]
        record["review_template"] = template
        packet_by_case_id[case_id] = record
    if not packet_by_case_id:
        raise ValueError("no selected review cases match --primary-category")
    records_by_case_id = _load_existing(args.output, packet_by_case_id) if args.resume else {}
    pending = [
        packet_by_case_id[case_id]
        for case_id in sorted(packet_by_case_id)
        if case_id not in records_by_case_id
    ]
    checkpoint_every = max(1, args.checkpoint_every)
    completed_since_checkpoint = 0
    failed_case_ids = []

    def checkpoint() -> None:
        write_jsonl(args.output, [records_by_case_id[key] for key in sorted(records_by_case_id)])
        print(f"Checkpointed {len(records_by_case_id)}/{len(packet_by_case_id)} automated audit records")

    def review_packet(record: dict) -> AutomatedReview:
        return LLMAutomatedReviewer(
            model=args.model,
            max_attempts=args.max_attempts,
            reviewer_id=args.reviewer_id,
            reviewer_kind=args.reviewer_kind,
            review_protocol=args.review_protocol,
        ).review(record)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(review_packet, record): record for record in pending}
        for future in as_completed(futures):
            record = futures[future]
            case_id = record["case_id"]
            try:
                review = future.result()
                records_by_case_id[case_id] = {
                    "case_id": case_id,
                    "automated_review": review.model_dump(mode="json"),
                }
            except Exception as exc:
                failed_case_ids.append(case_id)
                records_by_case_id[case_id] = _pending_record(record, args, exc)
                print(f"Automated audit pending for {case_id}: {exc}")
            completed_since_checkpoint += 1
            if completed_since_checkpoint >= checkpoint_every:
                checkpoint()
                completed_since_checkpoint = 0

    checkpoint()
    statuses = [
        row["automated_review"]["status"]
        for row in records_by_case_id.values()
    ]
    decisions = {
        case_id: row["automated_review"]["status"].upper()
        for case_id, row in sorted(records_by_case_id.items())
    }
    rejected_reasons = {
        case_id: row["automated_review"].get("notes", "")
        for case_id, row in sorted(records_by_case_id.items())
        if row["automated_review"]["status"] == "rejected"
    }
    write_json(args.summary_output, {
        "assessment_type": "automated agent assessment",
        "reviewer_id": args.reviewer_id,
        "reviewer_kind": args.reviewer_kind,
        "review_protocol": args.review_protocol,
        "primary_categories": sorted(allowed_categories),
        "reviewed_case_ids": sorted(records_by_case_id),
        "decision_by_case": decisions,
        "rejected_reasons": rejected_reasons,
        "overall_decision": (
            "APPROVED" if all(value == "APPROVED" for value in decisions.values())
            else "REJECTED" if any(value == "REJECTED" for value in decisions.values())
            else "PENDING"
        ),
    })
    print(
        f"Wrote {len(records_by_case_id)} automated agent assessments to {args.output}; "
        f"approved={statuses.count('approved')}, rejected={statuses.count('rejected')}, "
        f"pending={statuses.count('pending')}. No human expert review was performed."
    )
    if args.run_manifest:
        write_json(args.run_manifest, {
            "review_mode": "automated_only",
            "human_review_status": "not_performed",
            "review_packet_path": str(args.review_packet),
            "review_packet_sha256": sha256_file(args.review_packet),
            "candidates_path": str(args.candidates),
            "candidates_sha256": sha256_file(args.candidates),
            "judge_assessments_path": str(args.judge_assessments),
            "judge_assessments_sha256": sha256_file(args.judge_assessments),
            "primary_categories": sorted(allowed_categories),
            "automated_review_protocol": args.review_protocol,
            "reviewer_id": args.reviewer_id,
            "reviewer_kind": args.reviewer_kind,
            "review_model": args.model,
            "max_attempts": args.max_attempts,
            "workers": args.workers,
            "completed_assessments": len(records_by_case_id),
            "failed_case_ids": sorted(failed_case_ids),
            "automated_reviews_sha256": sha256_file(args.output),
        })


if __name__ == "__main__":
    main()
