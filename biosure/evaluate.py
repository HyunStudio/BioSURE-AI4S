"""Gold-separated evaluation for public challenge cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .baselines import identity_baseline, schema_locality_baseline, hash_evidence_baseline, evidence_reconstruction_baseline
from .gate import Decision, decide
from .receipts import make_receipt
from .schema import Candidate, DecisionRequest, parse_document, parse_request


@dataclass(frozen=True)
class DecisionRecord:
    request: DecisionRequest
    decision: Decision
    receipt: dict


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    source_graph_id: str
    operation: str
    action: str
    exact_auto: bool
    incorrect_auto: bool
    wrong_executable_candidates_total: int
    wrong_executable_candidates_accepted: int
    decision_receipt_sha256: str
    schema_baseline_auto: bool
    schema_baseline_incorrect: bool
    identity_baseline_auto: bool
    condition: str
    hash_baseline_auto: bool
    hash_baseline_incorrect: bool
    reconstruction_baseline_auto: bool
    reconstruction_baseline_incorrect: bool


def decide_case(request_path: Path) -> DecisionRecord:
    request = parse_request(json.loads(request_path.read_text(encoding="utf-8")))
    decision = decide(request)
    receipt = make_receipt(request, decision, "biosure-blind-v2")
    return DecisionRecord(request, decision, receipt)


def score_case(record: DecisionRecord, gold_path: Path) -> CaseResult:
    gold = parse_document(json.loads(gold_path.read_text(encoding="utf-8")))
    if gold.record_id != record.request.damaged.record_id:
        raise ValueError("gold record_id mismatch")
    wrong_executable = 0
    for candidate in record.request.candidates:
        single = DecisionRequest(record.request.case_id, record.request.damaged, (candidate,), record.request.evidence)
        if schema_locality_baseline(single).action == "AUTO_REPAIR" and candidate.document != gold:
            wrong_executable += 1
    selected = next(
        (item for item in record.request.candidates if item.candidate_id == record.decision.candidate_id),
        None,
    )
    auto = record.decision.action == "AUTO_REPAIR"
    exact = auto and selected is not None and selected.document == gold
    incorrect = auto and not exact
    schema_decision = schema_locality_baseline(record.request)
    schema_candidate = next(
        (item for item in record.request.candidates if item.candidate_id == schema_decision.candidate_id),
        None,
    )
    schema_auto = schema_decision.action == "AUTO_REPAIR"
    def comparator_score(policy):
        decision = policy(record.request)
        selected = next((item for item in record.request.candidates if item.candidate_id == decision.candidate_id), None)
        auto = decision.action == "AUTO_REPAIR"
        return auto, auto and (selected is None or selected.document != gold)
    hash_auto, hash_incorrect = comparator_score(hash_evidence_baseline)
    reconstruction_auto, reconstruction_incorrect = comparator_score(evidence_reconstruction_baseline)
    operations = {item.operation for item in record.request.candidates}
    operation = next(iter(operations)) if len(operations) == 1 else "MIXED_OR_NONE"
    return CaseResult(
        case_id=record.request.case_id,
        source_graph_id=record.request.damaged.record_id,
        operation=operation,
        action=record.decision.action,
        exact_auto=exact,
        incorrect_auto=incorrect,
        wrong_executable_candidates_total=wrong_executable,
        wrong_executable_candidates_accepted=int(incorrect),
        decision_receipt_sha256=record.receipt["receipt_sha256"],
        schema_baseline_auto=schema_auto,
        schema_baseline_incorrect=schema_auto and (schema_candidate is None or schema_candidate.document != gold),
        identity_baseline_auto=identity_baseline(record.request).action == "AUTO_REPAIR",
        condition=record.request.case_id.split("--", 1)[1] if "--" in record.request.case_id else "existing-probe",
        hash_baseline_auto=hash_auto, hash_baseline_incorrect=hash_incorrect,
        reconstruction_baseline_auto=reconstruction_auto, reconstruction_baseline_incorrect=reconstruction_incorrect,
    )


def summarize(results: Sequence[CaseResult]) -> dict:
    cases = len(results)
    automatic = sum(result.action == "AUTO_REPAIR" for result in results)
    exact = sum(result.exact_auto for result in results)
    errors = sum(result.incorrect_auto for result in results)
    operations = sorted({result.operation for result in results})
    return {
        "schema_version": "biosure.public-summary/1.1",
        "source_graphs": len({result.source_graph_id for result in results}),
        "cases": cases,
        "automatic": automatic,
        "exact_auto": exact,
        "incorrect_auto": errors,
        "abstentions": cases - automatic,
        "coverage": automatic / cases if cases else None,
        "accepted_error_rate": errors / automatic if automatic else None,
        "wrong_executable_candidates_total": sum(result.wrong_executable_candidates_total for result in results),
        "wrong_executable_candidates_accepted": sum(result.wrong_executable_candidates_accepted for result in results),
        "schema_locality_baseline": {
            "automatic": sum(result.schema_baseline_auto for result in results),
            "incorrect_auto": sum(result.schema_baseline_incorrect for result in results),
        },
        "identity_baseline": {"automatic": sum(result.identity_baseline_auto for result in results)},
        "hash_evidence_baseline": {
            "automatic": sum(result.hash_baseline_auto for result in results),
            "exact_auto": sum(result.hash_baseline_auto and not result.hash_baseline_incorrect for result in results),
            "incorrect_auto": sum(result.hash_baseline_incorrect for result in results),
        },
        "evidence_reconstruction_baseline": {
            "automatic": sum(result.reconstruction_baseline_auto for result in results),
            "exact_auto": sum(result.reconstruction_baseline_auto and not result.reconstruction_baseline_incorrect for result in results),
            "incorrect_auto": sum(result.reconstruction_baseline_incorrect for result in results),
        },
        "by_condition": {condition: {
            "cases": sum(result.condition == condition for result in results),
            "automatic": sum(result.condition == condition and result.action == "AUTO_REPAIR" for result in results),
            "exact_auto": sum(result.condition == condition and result.exact_auto for result in results),
            "incorrect_auto": sum(result.condition == condition and result.incorrect_auto for result in results),
        } for condition in sorted({result.condition for result in results})},
        "by_operation": {
            operation: {
                "cases": sum(result.operation == operation for result in results),
                "automatic": sum(result.operation == operation and result.action == "AUTO_REPAIR" for result in results),
                "incorrect_auto": sum(result.operation == operation and result.incorrect_auto for result in results),
            }
            for operation in operations
        },
    }
