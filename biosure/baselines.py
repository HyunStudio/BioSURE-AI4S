"""Labeled public comparators; these are not the original DKE policies."""

from __future__ import annotations

from .gate import Decision, _inserted_block, _removed_block
from .schema import Block, DecisionRequest, Document


def identity_baseline(request: DecisionRequest) -> Decision:
    return Decision("ABSTAIN", None, ("IDENTITY_NO_REPAIR",))


def schema_locality_baseline(request: DecisionRequest) -> Decision:
    structurally_valid = []
    for candidate in request.candidates:
        if candidate.operation == "INSERT_PARAGRAPH":
            diff = _inserted_block(request.damaged, candidate.document)
            valid = diff is not None and diff[1].kind == "paragraph"
        else:
            removed = _removed_block(request.damaged, candidate.document)
            valid = removed is not None and removed.kind == "paragraph"
        if valid:
            structurally_valid.append(candidate.candidate_id)
    if len(structurally_valid) == 1:
        return Decision("AUTO_REPAIR", structurally_valid[0], ())
    return Decision("ABSTAIN", None, ("NO_UNIQUE_STRUCTURAL_CANDIDATE",))


def _unique(ids: list[str]) -> Decision:
    if len(ids) == 1:
        return Decision("AUTO_REPAIR", ids[0], ())
    return Decision("ABSTAIN", None, ("NO_UNIQUE_REFERENCE_MATCH",))


def hash_evidence_baseline(request: DecisionRequest) -> Decision:
    """Same evidence, but compare content hashes only (no identity/position)."""
    valid = []
    for candidate in request.candidates:
        if candidate.operation == "INSERT_PARAGRAPH":
            diff = _inserted_block(request.damaged, candidate.document)
            supported = diff is not None and diff[1].kind == "paragraph" and any(
                item.text_sha256 == diff[1].text_sha256 for item in request.evidence.trusted_insertions)
        else:
            removed = _removed_block(request.damaged, candidate.document)
            supported = removed is not None and removed.kind == "paragraph" and any(
                block.kind == "paragraph" and block.text_sha256 == removed.text_sha256
                for block in candidate.document.blocks) and any(
                item.text_sha256 == removed.text_sha256 for item in request.evidence.trusted_identities)
        if supported:
            valid.append(candidate.candidate_id)
    return _unique(valid)


def evidence_reconstruction_baseline(request: DecisionRequest) -> Decision:
    """Independently reconstruct evidence-supported graphs, then compare whole graphs.

    No candidate-specific gate validators or global conflict veto are used.
    This strong comparator may tie the gate; that is reported, not hidden.
    """
    blocks = request.damaged.blocks
    ids = {block.block_id: i for i, block in enumerate(blocks)}
    expected: dict[str, list[Document]] = {"INSERT_PARAGRAPH": [], "REMOVE_DUPLICATE": []}
    for item in request.evidence.trusted_insertions:
        before, after = ids.get(item.before_id), ids.get(item.after_id)
        if before is None or after != before + 1 or item.block_id in ids:
            continue
        added = Block(item.block_id, "paragraph", item.text_sha256, 0, None)
        expected["INSERT_PARAGRAPH"].append(Document(request.damaged.record_id,
            blocks[:after] + (added,) + blocks[after:], request.damaged.citation_anchors))
    for item in request.evidence.trusted_identities:
        retained, duplicate = ids.get(item.retained_block_id), ids.get(item.duplicate_block_id)
        if retained is None or duplicate is None or retained == duplicate:
            continue
        if any(blocks[i].kind != "paragraph" or blocks[i].text_sha256 != item.text_sha256 for i in (retained, duplicate)):
            continue
        expected["REMOVE_DUPLICATE"].append(Document(request.damaged.record_id,
            blocks[:duplicate] + blocks[duplicate + 1:], request.damaged.citation_anchors))
    return _unique([candidate.candidate_id for candidate in request.candidates
                    if candidate.document in expected[candidate.operation]])
