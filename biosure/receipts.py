"""Deterministic, outcome-free decision receipts."""

from __future__ import annotations

from .gate import Decision
from .schema import DecisionRequest, sha256


def make_receipt(request: DecisionRequest, decision: Decision, rule_version: str) -> dict:
    if not rule_version:
        raise ValueError("rule_version required")
    candidates = {item.candidate_id: sha256(item.document.to_mapping()) for item in request.candidates}
    selected = next((item for item in request.candidates if item.candidate_id == decision.candidate_id), None)
    record = {
        "schema_version": "biosure.receipt/1.0",
        "case_id": request.case_id,
        "input_sha256": sha256(request.to_mapping()),
        "damaged_sha256": sha256(request.damaged.to_mapping()),
        "evidence_sha256": sha256(request.evidence.to_mapping()),
        "candidate_sha256": dict(sorted(candidates.items())),
        "configuration_sha256": sha256({"rule_version": rule_version}),
        "rule_version": rule_version,
        "decision": {
            "action": decision.action,
            "candidate_id": decision.candidate_id,
            "reason_codes": list(decision.reason_codes),
        },
        "selected_output_sha256": sha256(selected.document.to_mapping()) if selected else None,
    }
    record["receipt_sha256"] = sha256(record)
    return record
