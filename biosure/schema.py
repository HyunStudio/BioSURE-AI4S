"""Strict public decision input. No outcome or injected-corruption fields."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_KINDS = {"heading", "paragraph", "figure_caption", "table_caption", "reference"}
_OPERATIONS = {"INSERT_PARAGRAPH", "REMOVE_DUPLICATE"}


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def loads_json(text: str) -> Any:
    """Reject ambiguous duplicate fields and non-finite JSON numbers."""
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("non-finite JSON number")
    return json.loads(text, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _keys(value: Mapping[str, Any], required: set[str], name: str) -> None:
    unknown = set(value) - required
    missing = required - set(value)
    if unknown:
        raise ValueError(f"unknown {name} fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing {name} fields: {sorted(missing)}")


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _hash(value: object) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise ValueError("text_sha256 must be 64 lowercase hex characters")
    return value


def _list(value: object, name: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


@dataclass(frozen=True)
class Block:
    block_id: str
    kind: str
    text_sha256: str
    section_level: int
    target_id: str | None


@dataclass(frozen=True)
class Document:
    record_id: str
    blocks: tuple[Block, ...]
    citation_anchors: tuple[tuple[str, str], ...]

    def to_mapping(self) -> dict:
        return {
            "record_id": self.record_id,
            "blocks": [asdict(block) for block in self.blocks],
            "citation_anchors": [list(anchor) for anchor in self.citation_anchors],
        }


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    operation: str
    document: Document


@dataclass(frozen=True)
class TrustedInsertion:
    block_id: str
    text_sha256: str
    before_id: str
    after_id: str
    source_id: str


@dataclass(frozen=True)
class TrustedIdentity:
    retained_block_id: str
    duplicate_block_id: str
    text_sha256: str
    source_id: str


@dataclass(frozen=True)
class Evidence:
    trusted_insertions: tuple[TrustedInsertion, ...]
    trusted_identities: tuple[TrustedIdentity, ...]

    def to_mapping(self) -> dict:
        return {
            "trusted_insertions": [asdict(item) for item in self.trusted_insertions],
            "trusted_identities": [asdict(item) for item in self.trusted_identities],
        }


@dataclass(frozen=True)
class DecisionRequest:
    case_id: str
    damaged: Document
    candidates: tuple[Candidate, ...]
    evidence: Evidence

    def to_mapping(self) -> dict:
        return {
            "case_id": self.case_id,
            "damaged": self.damaged.to_mapping(),
            "candidates": [
                {"candidate_id": item.candidate_id, "operation": item.operation, "document": item.document.to_mapping()}
                for item in self.candidates
            ],
            "evidence": self.evidence.to_mapping(),
        }


def _block(value: object) -> Block:
    data = _mapping(value, "block")
    _keys(data, {"block_id", "kind", "text_sha256", "section_level", "target_id"}, "block")
    block_id = _nonempty(data["block_id"], "block_id")
    kind = data["kind"]
    if not isinstance(kind, str) or kind not in _KINDS:
        raise ValueError("unknown block kind")
    text_hash = _hash(data["text_sha256"])
    level = data["section_level"]
    if type(level) is not int or level < 0:
        raise ValueError("section_level must be a nonnegative integer")
    target_id = data["target_id"]
    if target_id is not None:
        target_id = _nonempty(target_id, "target_id")
    return Block(block_id, kind, text_hash, level, target_id)


def _document(value: object) -> Document:
    data = _mapping(value, "document")
    _keys(data, {"record_id", "blocks", "citation_anchors"}, "document")
    record_id = _nonempty(data["record_id"], "record_id")
    blocks = tuple(_block(item) for item in _list(data["blocks"], "blocks"))
    ids = [block.block_id for block in blocks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate block IDs")
    anchors: list[tuple[str, str]] = []
    for item in _list(data["citation_anchors"], "citation_anchors"):
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("anchor must be a pair")
        pair = (_nonempty(item[0], "anchor source"), _nonempty(item[1], "anchor target"))
        if pair[0] not in ids or pair[1] not in ids:
            raise ValueError("dangling anchor")
        anchors.append(pair)
    if len(anchors) != len(set(anchors)):
        raise ValueError("duplicate anchor")
    return Document(record_id, blocks, tuple(anchors))


def parse_document(value: object) -> Document:
    """Parse a graph independently of a decision request."""
    return _document(value)


def _evidence(value: object) -> Evidence:
    data = _mapping(value, "evidence")
    _keys(data, {"trusted_insertions", "trusted_identities"}, "evidence")
    insertions = []
    for item in _list(data["trusted_insertions"], "trusted_insertions"):
        entry = _mapping(item, "trusted insertion")
        _keys(entry, {"block_id", "text_sha256", "before_id", "after_id", "source_id"}, "trusted insertion")
        insertions.append(
            TrustedInsertion(
                _nonempty(entry["block_id"], "block_id"),
                _hash(entry["text_sha256"]),
                _nonempty(entry["before_id"], "before_id"),
                _nonempty(entry["after_id"], "after_id"),
                _nonempty(entry["source_id"], "source_id"),
            )
        )
    identities = []
    for item in _list(data["trusted_identities"], "trusted_identities"):
        entry = _mapping(item, "trusted identity")
        _keys(entry, {"retained_block_id", "duplicate_block_id", "text_sha256", "source_id"}, "trusted identity")
        identities.append(
            TrustedIdentity(
                _nonempty(entry["retained_block_id"], "retained_block_id"),
                _nonempty(entry["duplicate_block_id"], "duplicate_block_id"),
                _hash(entry["text_sha256"]),
                _nonempty(entry["source_id"], "source_id"),
            )
        )
    return Evidence(tuple(insertions), tuple(identities))


def parse_request(payload: Mapping[str, object]) -> DecisionRequest:
    data = _mapping(payload, "request")
    _keys(data, {"case_id", "damaged", "candidates", "evidence"}, "request")
    candidates = []
    for item in _list(data["candidates"], "candidates"):
        entry = _mapping(item, "candidate")
        _keys(entry, {"candidate_id", "operation", "document"}, "candidate")
        operation = entry["operation"]
        if not isinstance(operation, str) or operation not in _OPERATIONS:
            raise ValueError("unknown operation")
        candidates.append(
            Candidate(_nonempty(entry["candidate_id"], "candidate_id"), operation, _document(entry["document"]))
        )
    ids = [item.candidate_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate candidate IDs")
    return DecisionRequest(_nonempty(data["case_id"], "case_id"), _document(data["damaged"]), tuple(candidates), _evidence(data["evidence"]))
