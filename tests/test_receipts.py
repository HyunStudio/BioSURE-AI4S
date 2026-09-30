from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.gate import decide
from biosure.receipts import make_receipt
from biosure.schema import canonical_bytes, parse_request
from test_gate import insertion


def test_receipt_is_deterministic_and_outcome_free() -> None:
    request = parse_request(insertion())
    receipt = make_receipt(request, decide(request), "biosure-blind-v1")
    assert canonical_bytes(receipt) == canonical_bytes(make_receipt(request, decide(request), "biosure-blind-v1"))
    encoded = json.dumps(receipt)
    assert "gold" not in encoded
    assert "correct" not in encoded
    assert receipt["decision"]["action"] == "AUTO_REPAIR"
    assert len(receipt["candidate_sha256"]) == 1


def test_receipt_changes_when_candidate_payload_changes() -> None:
    good = insertion()
    bad = copy.deepcopy(good)
    bad["candidates"][0]["document"]["blocks"][1]["text_sha256"] = "f" * 64
    good_request = parse_request(good)
    bad_request = parse_request(bad)
    good_receipt = make_receipt(good_request, decide(good_request), "biosure-blind-v1")
    bad_receipt = make_receipt(bad_request, decide(bad_request), "biosure-blind-v1")
    assert good_receipt["candidate_sha256"] != bad_receipt["candidate_sha256"]
    assert good_receipt["decision"]["action"] != bad_receipt["decision"]["action"]
