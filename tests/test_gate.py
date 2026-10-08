from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.gate import decide
from biosure.schema import parse_request


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def block(block_id: str, text: str) -> dict:
    return {"block_id": block_id, "kind": "paragraph", "text_sha256": h(text), "section_level": 0, "target_id": None}


def insertion() -> dict:
    damaged = {"record_id": "source-1", "blocks": [block("p1", "alpha"), block("p3", "gamma")], "citation_anchors": []}
    candidate = copy.deepcopy(damaged)
    candidate["blocks"].insert(1, block("p2", "beta"))
    return {
        "case_id": "insert-1",
        "damaged": damaged,
        "candidates": [{"candidate_id": "good", "operation": "INSERT_PARAGRAPH", "document": candidate}],
        "evidence": {
            "trusted_insertions": [{"block_id": "p2", "text_sha256": h("beta"), "before_id": "p1", "after_id": "p3", "source_id": "independent-registry"}],
            "trusted_identities": [],
        },
    }


def duplicate() -> dict:
    damaged = {
        "record_id": "source-2",
        "blocks": [block("p1", "alpha"), block("p1copy", "alpha"), block("p2", "beta")],
        "citation_anchors": [],
    }
    candidate = copy.deepcopy(damaged)
    candidate["blocks"].pop(1)
    return {
        "case_id": "duplicate-1",
        "damaged": damaged,
        "candidates": [{"candidate_id": "good", "operation": "REMOVE_DUPLICATE", "document": candidate}],
        "evidence": {
            "trusted_insertions": [],
            "trusted_identities": [{"retained_block_id": "p1", "duplicate_block_id": "p1copy", "text_sha256": h("alpha"), "source_id": "independent-registry"}],
        },
    }


def test_valid_insertion_auto_repairs() -> None:
    decision = decide(parse_request(insertion()))
    assert (decision.action, decision.candidate_id, decision.reason_codes) == ("AUTO_REPAIR", "good", ())


def test_valid_duplicate_removal_auto_repairs() -> None:
    decision = decide(parse_request(duplicate()))
    assert (decision.action, decision.candidate_id) == ("AUTO_REPAIR", "good")


def test_duplicate_removal_rejects_noncanonical_removed_paragraph() -> None:
    for field, value in (("section_level", 1), ("target_id", "figure-7")):
        payload = duplicate()
        payload["damaged"]["blocks"][1][field] = value
        assert decide(parse_request(payload)).action == "ABSTAIN"


def test_duplicate_removal_rejects_noncanonical_retained_paragraph() -> None:
    for field, value in (("section_level", 1), ("target_id", "figure-7")):
        payload = duplicate()
        payload["damaged"]["blocks"][0][field] = value
        payload["candidates"][0]["document"]["blocks"][0][field] = value
        assert decide(parse_request(payload)).action == "ABSTAIN"


def test_wrong_executable_payload_abstains_without_source_change() -> None:
    good = insertion()
    bad = copy.deepcopy(good)
    bad["candidates"][0]["document"]["blocks"][1]["text_sha256"] = h("substituted")
    assert good["damaged"] == bad["damaged"]
    assert good["evidence"] == bad["evidence"]
    assert decide(parse_request(good)).action == "AUTO_REPAIR"
    assert decide(parse_request(bad)).action == "ABSTAIN"


def test_wrong_surviving_neighbors_abstains() -> None:
    payload = insertion()
    payload["candidates"][0]["document"]["blocks"] = [
        payload["candidates"][0]["document"]["blocks"][1],
        *payload["damaged"]["blocks"],
    ]
    assert decide(parse_request(payload)).action == "ABSTAIN"


def test_unauthorized_duplicate_removal_abstains() -> None:
    payload = duplicate()
    payload["candidates"][0]["document"]["blocks"].pop(0)
    payload["candidates"][0]["document"]["blocks"].insert(0, block("p1copy", "alpha"))
    assert decide(parse_request(payload)).action == "ABSTAIN"


def test_two_valid_candidates_abstain_independent_of_order() -> None:
    payload = insertion()
    other = copy.deepcopy(payload["candidates"][0])
    other["candidate_id"] = "also-good"
    payload["candidates"].append(other)
    first = decide(parse_request(payload))
    payload["candidates"].reverse()
    second = decide(parse_request(payload))
    assert first == second
    assert first.action == "ABSTAIN"
    assert "AMBIGUOUS_CANDIDATES" in first.reason_codes


def test_missing_evidence_abstains() -> None:
    payload = insertion()
    payload["evidence"]["trusted_insertions"] = []
    result = decide(parse_request(payload))
    assert result.action == "ABSTAIN"
    assert result.candidate_id is None


def test_unrelated_graph_edit_abstains() -> None:
    payload = insertion()
    payload["candidates"][0]["document"]["blocks"][0]["text_sha256"] = h("changed neighbor")
    assert decide(parse_request(payload)).action == "ABSTAIN"


def test_conflicting_insertion_evidence_abstains_before_candidate_selection() -> None:
    payload = insertion()
    conflicting = copy.deepcopy(payload["evidence"]["trusted_insertions"][0])
    conflicting.update(text_sha256=h("other"), source_id="second-registry")
    payload["evidence"]["trusted_insertions"].append(conflicting)
    decision = decide(parse_request(payload))
    assert decision.action == "ABSTAIN"
    assert "CONFLICTING_EVIDENCE" in decision.reason_codes


def test_reversed_duplicate_identity_abstains() -> None:
    payload = duplicate()
    reversed_entry = copy.deepcopy(payload["evidence"]["trusted_identities"][0])
    reversed_entry["retained_block_id"], reversed_entry["duplicate_block_id"] = (
        reversed_entry["duplicate_block_id"], reversed_entry["retained_block_id"]
    )
    reversed_entry["source_id"] = "second-registry"
    payload["evidence"]["trusted_identities"].append(reversed_entry)
    decision = decide(parse_request(payload))
    assert decision.action == "ABSTAIN"
    assert "CONFLICTING_EVIDENCE" in decision.reason_codes


def test_insertion_with_unsupported_structural_metadata_abstains() -> None:
    for key, value in (("section_level", 99), ("target_id", "nonexistent")):
        payload = insertion()
        payload["candidates"][0]["document"]["blocks"][1][key] = value
        assert decide(parse_request(payload)).action == "ABSTAIN"
