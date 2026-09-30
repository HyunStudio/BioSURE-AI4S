"""Candidate-dependent structural gate; no gold or known-corruption input."""

from __future__ import annotations

from dataclasses import dataclass

from .schema import Candidate, DecisionRequest, Document


@dataclass(frozen=True)
class Decision:
    action: str
    candidate_id: str | None
    reason_codes: tuple[str, ...]


def _inserted_block(damaged: Document, candidate: Document):
    if candidate.record_id != damaged.record_id or candidate.citation_anchors != damaged.citation_anchors:
        return None
    if len(candidate.blocks) != len(damaged.blocks) + 1:
        return None
    for index, block in enumerate(candidate.blocks):
        if candidate.blocks[:index] + candidate.blocks[index + 1 :] == damaged.blocks:
            return index, block
    return None


def _removed_block(damaged: Document, candidate: Document):
    if candidate.record_id != damaged.record_id or candidate.citation_anchors != damaged.citation_anchors:
        return None
    if len(candidate.blocks) != len(damaged.blocks) - 1:
        return None
    for index, block in enumerate(damaged.blocks):
        if damaged.blocks[:index] + damaged.blocks[index + 1 :] == candidate.blocks:
            return block
    return None


def _valid_insert(request: DecisionRequest, candidate: Candidate) -> bool:
    diff = _inserted_block(request.damaged, candidate.document)
    if diff is None:
        return False
    index, block = diff
    if (block.kind != "paragraph" or block.section_level != 0 or block.target_id is not None
            or index == 0 or index == len(candidate.document.blocks) - 1):
        return False
    before = candidate.document.blocks[index - 1].block_id
    after = candidate.document.blocks[index + 1].block_id
    return any(
        item.block_id == block.block_id
        and item.text_sha256 == block.text_sha256
        and item.before_id == before
        and item.after_id == after
        for item in request.evidence.trusted_insertions
    )


def _conflicting_evidence(request: DecisionRequest) -> bool:
    insertions: dict[str, tuple[str, str, str]] = {}
    for item in request.evidence.trusted_insertions:
        claim = (item.text_sha256, item.before_id, item.after_id)
        previous = insertions.setdefault(item.block_id, claim)
        if previous != claim:
            return True
    identities: dict[frozenset[str], tuple[str, str, str]] = {}
    for item in request.evidence.trusted_identities:
        pair = frozenset((item.retained_block_id, item.duplicate_block_id))
        claim = (item.retained_block_id, item.duplicate_block_id, item.text_sha256)
        previous = identities.setdefault(pair, claim)
        if previous != claim:
            return True
    return False


def _valid_remove(request: DecisionRequest, candidate: Candidate) -> bool:
    removed = _removed_block(request.damaged, candidate.document)
    if removed is None or removed.kind != "paragraph":
        return False
    retained = {block.block_id: block for block in candidate.document.blocks}
    return any(
        item.duplicate_block_id == removed.block_id
        and item.retained_block_id in retained
        and retained[item.retained_block_id].kind == "paragraph"
        and retained[item.retained_block_id].text_sha256 == removed.text_sha256 == item.text_sha256
        for item in request.evidence.trusted_identities
    )


def decide(request: DecisionRequest) -> Decision:
    if _conflicting_evidence(request):
        return Decision("ABSTAIN", None, ("CONFLICTING_EVIDENCE",))
    valid = []
    for candidate in request.candidates:
        if candidate.operation == "INSERT_PARAGRAPH" and _valid_insert(request, candidate):
            valid.append(candidate.candidate_id)
        elif candidate.operation == "REMOVE_DUPLICATE" and _valid_remove(request, candidate):
            valid.append(candidate.candidate_id)
    if len(valid) == 1:
        return Decision("AUTO_REPAIR", valid[0], ())
    if len(valid) > 1:
        return Decision("ABSTAIN", None, ("AMBIGUOUS_CANDIDATES",))
    return Decision("ABSTAIN", None, ("NO_VALID_CANDIDATE",))
