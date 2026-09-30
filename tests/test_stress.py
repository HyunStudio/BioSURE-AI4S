from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.baselines import hash_evidence_baseline, evidence_reconstruction_baseline
from biosure.evaluate import DecisionRecord, score_case, summarize
from biosure.gate import decide
from biosure.receipts import make_receipt
from biosure.schema import parse_document, parse_request
from scripts.build_stress_challenge import build_cases, emit

ROOT = Path(__file__).resolve().parents[1]


def case(name):
    return parse_request(json.loads((ROOT / "fixtures/challenge" / (name + ".json")).read_text(encoding="utf-8")))


def test_equal_evidence_comparators_accept_correct_operations():
    for name in ("01-insertion-good", "07-duplicate-good"):
        request = case(name)
        assert hash_evidence_baseline(request).action == "AUTO_REPAIR"
        assert evidence_reconstruction_baseline(request).action == "AUTO_REPAIR"


def test_hash_only_lacks_location_and_identity_checks():
    for name in ("03-insertion-wrong-location", "04-insertion-wrong-id", "08-duplicate-remove-retained"):
        request = case(name)
        assert hash_evidence_baseline(request).action == "AUTO_REPAIR"
        assert evidence_reconstruction_baseline(request).action == "ABSTAIN"


def test_stress_suite_reports_forged_evidence_failure_against_unchanged_gold(tmp_path):
    cases = build_cases()
    assert len(cases) == 168
    assert len({request["damaged"]["record_id"] for request, _ in cases.values()}) == 12
    results = []
    for name, (mapping, gold) in cases.items():
        request = parse_request(mapping)
        parse_document(gold)
        decision = decide(request)
        path = tmp_path / "gold.json"
        path.write_text(json.dumps(gold), encoding="utf-8")
        result = score_case(DecisionRecord(request, decision, make_receipt(request, decision, "biosure-blind-v2")), path)
        results.append(result)
        if name.endswith("--forged-evidence"):
            assert result.incorrect_auto is True
            assert evidence_reconstruction_baseline(request).action == "AUTO_REPAIR"
    summary = summarize(results)
    assert (summary["automatic"], summary["exact_auto"], summary["incorrect_auto"]) == (36, 24, 12)
    assert summary["by_condition"]["forged-evidence"]["incorrect_auto"] == 12
    assert summary["evidence_reconstruction_baseline"]["incorrect_auto"] == 12
    assert summary["by_condition"]["insert-good"]["exact_auto"] == 12


def test_generator_is_byte_reproducible_and_checked_in(tmp_path):
    emit(tmp_path / "one")
    emit(tmp_path / "two")
    for path in (tmp_path / "one").rglob("*.json"):
        relative = path.relative_to(tmp_path / "one")
        assert path.read_bytes() == (tmp_path / "two" / relative).read_bytes()
        assert path.read_bytes() == (ROOT / "fixtures" / relative).read_bytes()


def test_summary_exposes_equal_evidence_tie_on_article_set():
    from biosure.evaluate import decide_case
    fixtures = ROOT / "fixtures"
    results = [score_case(decide_case(path), fixtures / "article_gold" / path.name)
               for path in sorted((fixtures / "article_challenge").glob("*.json"))]
    summary = summarize(results)
    assert summary["hash_evidence_baseline"] == {"automatic": 3, "exact_auto": 3, "incorrect_auto": 0}
    assert summary["evidence_reconstruction_baseline"] == {"automatic": 3, "exact_auto": 3, "incorrect_auto": 0}
