"""Bounded paragraph conversion QC. References are declared, not authenticated."""

from __future__ import annotations

import hashlib
from collections import Counter
from difflib import SequenceMatcher

from .gate import decide
from .receipts import make_receipt
from .schema import DecisionRequest, parse_request, sha256


def decision_payload(request: DecisionRequest) -> dict:
    decision = decide(request)
    selected = next((item for item in request.candidates if item.candidate_id == decision.candidate_id), None)
    return {"request": request.to_mapping(),
            "decision": {"action": decision.action, "candidate_id": decision.candidate_id,
                         "reason_codes": list(decision.reason_codes)},
            "selected_output": selected.document.to_mapping() if selected else None,
            "receipt": make_receipt(request, decision, "biosure-blind-v2")}


def _paragraphs(value: object) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("supply 1 to 128 paragraphs per input")
    result = []
    for paragraph in value:
        if not isinstance(paragraph, str) or len(paragraph) > 4096:
            raise ValueError("each paragraph must be text of at most 4096 characters")
        normalized = " ".join(paragraph.split())
        if not normalized:
            raise ValueError("paragraphs must be nonempty")
        result.append(normalized)
    return result


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _block(block_id: str, text: str) -> dict:
    return {"block_id": block_id, "kind": "paragraph", "text_sha256": _digest(text),
            "section_level": 0, "target_id": None}


def run_workflow(payload: dict) -> dict:
    """Propose one internal omission or exact-extra-duplicate edit; no gold input."""
    if not isinstance(payload, dict) or set(payload) != {"record_id", "reference_paragraphs", "observed_paragraphs"}:
        raise ValueError("workflow requires record_id, reference_paragraphs and observed_paragraphs only")
    record_id = payload["record_id"]
    if not isinstance(record_id, str) or not record_id.strip() or len(record_id) > 128:
        raise ValueError("record_id must be nonempty text of at most 128 characters")
    reference = _paragraphs(payload["reference_paragraphs"])
    observed = _paragraphs(payload["observed_paragraphs"])
    if sum(map(len, reference + observed)) > 262144:
        raise ValueError("combined paragraph text exceeds limit")
    ref_blocks = [_block(f"r{i + 1}", text) for i, text in enumerate(reference)]
    ref_by_hash = {block["text_sha256"]: block for block in ref_blocks}
    used = Counter()
    obs_blocks = []
    for i, text in enumerate(observed):
        digest = _digest(text)
        block_id = ref_by_hash[digest]["block_id"] if digest in ref_by_hash and used[digest] == 0 else f"x{i + 1}"
        obs_blocks.append(_block(block_id, text))
        used[digest] += 1
    damaged = {"record_id": record_id, "blocks": obs_blocks, "citation_anchors": []}
    restored = {"record_id": record_id, "blocks": ref_blocks, "citation_anchors": []}
    request = {"case_id": record_id + ":paragraph-qc", "damaged": damaged, "candidates": [],
               "evidence": {"trusted_insertions": [], "trusted_identities": []}}
    source_id = "declared-reference:" + sha256(reference)
    status = "UNSUPPORTED_DIFFERENCE"
    applied_change = None
    if len(ref_by_hash) != len(reference):
        status = "AMBIGUOUS_REFERENCE"
    elif reference == observed:
        status = "NO_CHANGE"
    elif len(observed) == len(reference) - 1:
        missing = next((i for i in range(len(reference)) if reference[:i] + reference[i + 1:] == observed), None)
        if missing is not None:
            if missing == 0 or missing == len(reference) - 1:
                status = "BOUNDARY_OMISSION"
            else:
                status = "CANDIDATE_PROPOSED"
                applied_change = {"kind": "missing", "reference_span": [missing, missing + 1],
                                  "observed_span": [missing, missing]}
                block = ref_blocks[missing]
                request["evidence"]["trusted_insertions"] = [{"block_id": block["block_id"],
                    "text_sha256": block["text_sha256"], "before_id": ref_blocks[missing - 1]["block_id"],
                    "after_id": ref_blocks[missing + 1]["block_id"], "source_id": source_id}]
                request["candidates"] = [{"candidate_id": "reference-insertion", "operation": "INSERT_PARAGRAPH", "document": restored}]
    elif len(observed) == len(reference) + 1:
        possible = [i for i, text in enumerate(observed)
                    if observed[:i] + observed[i + 1:] == reference and _digest(text) in ref_by_hash]
        # Adjacent identical copies have equivalent normalized outputs; keep
        # the first occurrence. Non-adjacent duplicates need alignment after
        # selecting the extra, not greedy first-hash identity assignment.
        removed = possible[-1] if possible else None
        if removed is not None:
            obs_blocks = []
            ref_index = 0
            for i, text in enumerate(observed):
                if i == removed:
                    obs_blocks.append(_block(f"x{i + 1}", text))
                else:
                    obs_blocks.append(ref_blocks[ref_index])
                    ref_index += 1
            request["damaged"] = {**damaged, "blocks": obs_blocks}
            status = "CANDIDATE_PROPOSED"
            applied_change = {"kind": "extra", "reference_span": [removed, removed],
                              "observed_span": [removed, removed + 1]}
            duplicate = obs_blocks[removed]
            retained = ref_by_hash[duplicate["text_sha256"]]
            request["evidence"]["trusted_identities"] = [{"retained_block_id": retained["block_id"],
                "duplicate_block_id": duplicate["block_id"], "text_sha256": duplicate["text_sha256"], "source_id": source_id}]
            request["candidates"] = [{"candidate_id": "reference-deduplication", "operation": "REMOVE_DUPLICATE", "document": restored}]
    result = decision_payload(parse_request(request))
    changes = [{"kind": {"delete": "missing", "insert": "extra", "replace": "changed"}[tag],
                "reference_span": [a, b], "observed_span": [c, d]}
               for tag, a, b, c, d in SequenceMatcher(None, reference, observed, autojunk=False).get_opcodes()
               if tag != "equal"]
    if result["decision"]["action"] == "AUTO_REPAIR" and applied_change is not None:
        changes = [applied_change]
    return {"mode": "declared_reference_paragraph_qc", "adapter_version": "biosure-paragraph-v1",
            "adapter_status": status, "reference_sha256": sha256(reference), "observed_sha256": sha256(observed),
            "review_changes": changes,
            "reference_paragraphs": reference, "observed_paragraphs": observed,
            "reference_assumption": "User-supplied reference is not authenticated; consistency is not biological correctness.",
            "selected_paragraphs": reference if result["decision"]["action"] == "AUTO_REPAIR" else None, **result}


def run_proposal(payload: dict) -> dict:
    """Validate untrusted upstream text, never replace it with a generated repair.

    Producer identity is deliberately absent: a pasted response is not evidence
    that any specific model ran. Reference and observations remain locked inputs.
    """
    required = {"record_id", "reference_paragraphs", "observed_paragraphs", "proposed_paragraphs"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("proposal requires record_id, reference_paragraphs, observed_paragraphs and proposed_paragraphs only")
    proposed = _paragraphs(payload["proposed_paragraphs"])
    original = run_workflow({key: value for key, value in payload.items() if key != "proposed_paragraphs"})
    if sum(map(len, proposed + original["reference_paragraphs"] + original["observed_paragraphs"])) > 262144:
        raise ValueError("combined proposal paragraph text exceeds limit")
    request = original["request"]
    if request["candidates"]:
        reference_blocks = [_block(f"r{i + 1}", text) for i, text in enumerate(original["reference_paragraphs"])]
        by_hash = {block["text_sha256"]: block for block in reference_blocks}
        used = Counter()
        blocks = []
        for i, text in enumerate(proposed):
            digest = _digest(text)
            block = by_hash[digest] if digest in by_hash and not used[digest] else _block(f"p{i + 1}", text)
            blocks.append(block)
            used[digest] += 1
        candidate = request["candidates"][0]
        request["candidates"] = [{**candidate, "candidate_id": "upstream-proposal",
            "document": {**candidate["document"], "blocks": blocks}}]
    checked = decision_payload(parse_request(request))
    automatic = checked["decision"]["action"] == "AUTO_REPAIR"
    binding = {"schema_version": "biosure.proposal-receipt/1.0",
        "reference_sha256": original["reference_sha256"], "observed_sha256": original["observed_sha256"],
        "proposal_sha256": sha256(proposed), "gate_receipt_sha256": checked["receipt"]["receipt_sha256"],
        "adapter_version": "biosure-proposal-v1"}
    return {**original, **checked, "mode": "untrusted_upstream_proposal_qc",
        "proposal_receipt": {**binding, "receipt_sha256": sha256(binding)},
        "adapter_status": "PROPOSAL_ACCEPTED" if automatic else "PROPOSAL_REJECTED",
        "original_adapter_status": original["adapter_status"],
        "proposed_paragraphs": proposed, "proposal_sha256": sha256(proposed),
        "producer_assumption": "Pasted proposal origin is not authenticated; no model performance is inferred.",
        "selected_paragraphs": proposed if automatic else None}
