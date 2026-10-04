"""Offline learned alignment that proposes declared-reference text for review.

The model selects correspondences, not scientifically correct wording. Its
candidate is never an edit authority and is checked by the existing gate.
"""

from __future__ import annotations

from .ml_review import review_paragraphs
from .schema import sha256
from .workflow import run_proposal


def propose_learned(payload: dict, model: dict) -> dict:
    """Return a review-only proposal when correspondence is unambiguous.

    A successful candidate copies the entire *declared* reference sequence.
    This deliberately does not imply that the reference was authenticated.
    """
    review = review_paragraphs(payload, model)
    matches = review["correspondences"]
    indices = [match["reference_index"] for match in matches]
    if any(match["ambiguous"] for match in matches):
        reason = "AMBIGUOUS_MATCH"
    elif any(not match["above_threshold"] for match in matches):
        reason = "LOW_CONFIDENCE"
    elif any(left >= right for left, right in zip(indices, indices[1:])):
        reason = "NON_MONOTONIC_ALIGNMENT"
    else:
        reason = "MATCHED_DECLARED_REFERENCE"

    proposal = review["reference_paragraphs"] if reason == "MATCHED_DECLARED_REFERENCE" else None
    proposal_check = None
    if proposal is not None:
        proposal_check = run_proposal({"record_id": payload["record_id"],
                                       "reference_paragraphs": review["reference_paragraphs"],
                                       "observed_paragraphs": review["observed_paragraphs"],
                                       "proposed_paragraphs": proposal})
    binding = {"schema_version": "biosure.learned-upstream-receipt/1.0",
               "model_sha256": sha256(model),
               "reference_sha256": review["reference_sha256"],
               "observed_sha256": review["observed_sha256"],
               "proposal_sha256": sha256(proposal) if proposal is not None else None,
               "proposal_gate_receipt_sha256": (proposal_check["receipt"]["receipt_sha256"]
                                                if proposal_check is not None else None)}
    return {"mode": "learned_upstream_proposal",
            "reference_paragraphs": review["reference_paragraphs"],
            "observed_paragraphs": review["observed_paragraphs"],
            "reference_sha256": review["reference_sha256"],
            "observed_sha256": review["observed_sha256"],
            "reference_assumption": review["reference_assumption"],
            "review_changes": review["review_changes"],
            "correspondences": matches,
            "model": review["model"], "ml_receipt": review["ml_receipt"],
            "original_workflow_review": {
                "adapter_status": review["adapter_status"],
                "decision": review["decision"],
                "selected_paragraphs": review["selected_paragraphs"],
                "receipt": review["receipt"],
            },
            "proposal_status": "PROPOSED_FOR_REVIEW" if proposal is not None else "ABSTAIN",
            "proposal_reason": reason,
            "proposed_paragraphs": proposal,
            "proposal_check": proposal_check,
            "upstream_receipt": {**binding, "receipt_sha256": sha256(binding)},
            "upstream_authority": "The fitted model aligns units only. Proposed text is copied from the unauthenticated declared reference; the deterministic gate decides any supported edit."}
