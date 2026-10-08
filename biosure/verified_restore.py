"""Internal, bounded graph-edit selection from a reproducible source artifact.

The provider is not exposed to public request parsing. A successful result is
only a selection; no output has been written or real-world source authenticated.
"""

from __future__ import annotations

from .gate import Decision, decide
from .schema import (
    DecisionRequest, Document, Evidence, TrustedIdentity, TrustedInsertion,
    canonical_bytes, loads_json, parse_document, sha256,
)
from .verified_source import SourceKey, TrustedSourceProvider, verify_source_artifact


def _abstain(reason: str) -> dict:
    return {
        "decision": Decision("ABSTAIN", None, (reason,)),
        "selected_output": None, "source_binding": None, "receipt": None,
    }


def _ordinary(block) -> bool:
    return block.kind == "paragraph" and block.section_level == 0 and block.target_id is None


def _derived_evidence(request: DecisionRequest, source: Document, source_id: str) -> Evidence | None:
    candidate = request.candidates[0]
    damaged = request.damaged
    if (damaged.record_id != source.record_id
            or damaged.citation_anchors != source.citation_anchors):
        return None
    if candidate.operation == "INSERT_PARAGRAPH" and len(source.blocks) == len(damaged.blocks) + 1:
        matches = [index for index in range(len(source.blocks))
                   if source.blocks[:index] + source.blocks[index + 1:] == damaged.blocks]
        if len(matches) != 1 or matches[0] in (0, len(source.blocks) - 1):
            return None
        index = matches[0]
        block = source.blocks[index]
        if not _ordinary(block):
            return None
        return Evidence((TrustedInsertion(
            block.block_id, block.text_sha256, source.blocks[index - 1].block_id,
            source.blocks[index + 1].block_id, source_id,
        ),), ())
    if candidate.operation == "REMOVE_DUPLICATE" and len(damaged.blocks) == len(source.blocks) + 1:
        matches = [index for index in range(len(damaged.blocks))
                   if damaged.blocks[:index] + damaged.blocks[index + 1:] == source.blocks]
        if len(matches) != 1:
            return None
        removed = damaged.blocks[matches[0]]
        if not _ordinary(removed):
            return None
        retained = [block for block in source.blocks
                    if _ordinary(block) and block.text_sha256 == removed.text_sha256]
        if len(retained) != 1:
            return None
        return Evidence((), (TrustedIdentity(
            retained[0].block_id, removed.block_id, removed.text_sha256, source_id,
        ),))
    return None


def review_verified_restoration(
    request: DecisionRequest, key: SourceKey, provider: TrustedSourceProvider | None,
) -> dict:
    """Select one source-equal edit; discard *all* caller-supplied evidence."""
    if not isinstance(request, DecisionRequest) or len(request.candidates) != 1:
        return _abstain("UNSUPPORTED_CANDIDATE_SET")
    try:
        artifact = verify_source_artifact(key, provider)
    except Exception:
        return _abstain("SOURCE_PROVIDER_FAILED")
    if artifact is None:
        return _abstain("UNVERIFIED_SOURCE")
    candidate = request.candidates[0]
    if candidate.document != artifact.graph:
        return _abstain("SOURCE_GRAPH_MISMATCH")
    evidence = _derived_evidence(request, artifact.graph, artifact.raw_sha256)
    if evidence is None:
        return _abstain("UNSUPPORTED_OR_AMBIGUOUS_EDIT")
    rebuilt = DecisionRequest(request.case_id, request.damaged, request.candidates, evidence)
    decision = decide(rebuilt)
    if decision.action != "AUTO_REPAIR" or decision.candidate_id != candidate.candidate_id:
        return _abstain("GATE_ABSTAINED")
    try:
        selected = parse_document(loads_json(canonical_bytes(candidate.document.to_mapping()).decode("utf-8")))
        if selected != artifact.graph or sha256(selected.to_mapping()) != artifact.graph_sha256:
            return _abstain("CANONICAL_REPARSE_MISMATCH")
    except (ValueError, TypeError, UnicodeError):
        return _abstain("CANONICAL_REPARSE_FAILED")
    binding = {
        "record_id": key.record_id, "version_id": key.version_id, "scope_id": key.scope_id,
        "raw_sha256": artifact.raw_sha256, "graph_sha256": artifact.graph_sha256,
        "extractor_version": artifact.extractor_version,
    }
    return {
        "decision": decision, "selected_output": selected, "source_binding": binding,
        "receipt": {"rule_version": "verified-source-selection/1", "status": "SELECTED_NOT_WRITTEN",
                    "candidate_id": candidate.candidate_id, "source_binding": binding},
    }
