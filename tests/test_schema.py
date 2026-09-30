from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.schema import canonical_bytes, parse_request, sha256


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_request() -> dict:
    damaged = {
        "record_id": "source-1",
        "blocks": [
            {"block_id": "p1", "kind": "paragraph", "text_sha256": digest("a"), "section_level": 0, "target_id": None},
            {"block_id": "p3", "kind": "paragraph", "text_sha256": digest("c"), "section_level": 0, "target_id": None},
        ],
        "citation_anchors": [],
    }
    candidate = copy.deepcopy(damaged)
    candidate["blocks"].insert(
        1,
        {"block_id": "p2", "kind": "paragraph", "text_sha256": digest("b"), "section_level": 0, "target_id": None},
    )
    return {
        "case_id": "case-1",
        "damaged": damaged,
        "candidates": [{"candidate_id": "candidate-1", "operation": "INSERT_PARAGRAPH", "document": candidate}],
        "evidence": {
            "trusted_insertions": [
                {"block_id": "p2", "text_sha256": digest("b"), "before_id": "p1", "after_id": "p3", "source_id": "author-manifest-1"}
            ],
            "trusted_identities": [],
        },
    }


def test_parses_public_request() -> None:
    request = parse_request(valid_request())
    assert request.case_id == "case-1"
    assert request.damaged.record_id == "source-1"
    assert request.candidates[0].candidate_id == "candidate-1"


@pytest.mark.parametrize("field", ["gold", "corruption_spec", "removed_block", "original_value"])
def test_rejects_top_level_gold_and_spec(field: str) -> None:
    payload = valid_request()
    payload[field] = {}
    with pytest.raises(ValueError, match="unknown"):
        parse_request(payload)


@pytest.mark.parametrize(
    "location,field",
    [("candidate", "original_value"), ("candidate", "gold"), ("block", "removed_block"), ("evidence", "corruption_spec")],
)
def test_rejects_nested_original_value(location: str, field: str) -> None:
    payload = valid_request()
    target = {
        "candidate": payload["candidates"][0],
        "block": payload["damaged"]["blocks"][0],
        "evidence": payload["evidence"],
    }[location]
    target[field] = "oracle"
    with pytest.raises(ValueError, match="unknown"):
        parse_request(payload)


def test_rejects_duplicate_ids_and_bad_sha() -> None:
    payload = valid_request()
    payload["damaged"]["blocks"][1]["block_id"] = "p1"
    with pytest.raises(ValueError, match="duplicate"):
        parse_request(payload)

    payload = valid_request()
    payload["damaged"]["blocks"][0]["text_sha256"] = "A" * 64
    with pytest.raises(ValueError, match="sha256"):
        parse_request(payload)


def test_rejects_dangling_anchor_and_unknown_operation() -> None:
    payload = valid_request()
    payload["damaged"]["citation_anchors"] = [["p1", "missing"]]
    with pytest.raises(ValueError, match="anchor"):
        parse_request(payload)

    payload = valid_request()
    payload["candidates"][0]["operation"] = "ORACLE_REPAIR"
    with pytest.raises(ValueError, match="operation"):
        parse_request(payload)


def test_rejects_unhashable_kind_and_operation_as_validation_error() -> None:
    payload = valid_request()
    payload["damaged"]["blocks"][0]["kind"] = []
    with pytest.raises(ValueError, match="kind"):
        parse_request(payload)

    payload = valid_request()
    payload["candidates"][0]["operation"] = []
    with pytest.raises(ValueError, match="operation"):
        parse_request(payload)


def test_canonical_bytes_stable_across_key_order() -> None:
    assert canonical_bytes({"b": "한", "a": 1}) == b'{"a":1,"b":"\xed\x95\x9c"}\n'
    assert sha256({"b": "한", "a": 1}) == hashlib.sha256(b'{"a":1,"b":"\xed\x95\x9c"}\n').hexdigest()
