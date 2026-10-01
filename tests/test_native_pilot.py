"""Pilot decisions must be gold-blind and expose bad-reference copy risk."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from biosure.native_pilot import decide_inputs, score_decisions
from biosure.schema import canonical_bytes
from scripts.audit_release import _rights_metadata
from scripts.prepare_release import prepare
from scripts.verify_reproduction import verify


ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))


def _inputs():
    return {"schema_version": "biosure.native-pilot-inputs/1.0",
            "source": {"id": "one-pdf", "license_uri": "https://creativecommons.org/licenses/by/4.0/"},
            "cases": [
                {"case_id": "unchanged", "source_locator": "p1-title", "condition": "control",
                 "reference_paragraphs": ["A heading."], "observed_paragraphs": ["A heading."]},
                {"case_id": "spacing", "source_locator": "p1-abstract", "condition": "native_extraction_error",
                 "reference_paragraphs": ["A reference sentence."], "observed_paragraphs": ["A refer ence sentence."]},
                {"case_id": "false-reference", "source_locator": "p1-body", "condition": "native_extraction_error",
                 "reference_paragraphs": ["A false claim."], "observed_paragraphs": ["A true claim."]},
            ]}


def _gold(digest):
    return {"schema_version": "biosure.native-pilot-gold/1.0", "input_sha256": digest,
            "cases": [{"case_id": "unchanged", "gold_paragraphs": ["A heading."]},
                      {"case_id": "spacing", "gold_paragraphs": ["A reference sentence."]},
                      {"case_id": "false-reference", "gold_paragraphs": ["A true claim."]}]}


def test_decision_phase_needs_no_gold_and_compares_identical_records():
    decisions = decide_inputs(_inputs(), MODEL)
    assert [item["case_id"] for item in decisions["cases"]] == ["unchanged", "spacing", "false-reference"]
    assert all(set(item) == {"case_id", "condition", "observed_paragraphs", "biosure", "direct_copy", "diff_review", "learned_review"}
               for item in decisions["cases"])
    assert decisions["cases"][1]["biosure"]["action"] == "ABSTAIN"
    assert decisions["cases"][1]["direct_copy"]["output_paragraphs"] == ["A reference sentence."]
    assert decisions["cases"][1]["diff_review"]["action"] == "REVIEW"
    assert decisions["cases"][1]["learned_review"]["action"] == "REVIEW"
    assert "gold" not in json.dumps(decisions).lower()


def test_scoring_counts_control_separately_and_bad_reference_copy_as_error():
    decisions = decide_inputs(_inputs(), MODEL)
    scored = score_decisions(decisions, _gold(decisions["input_sha256"]))
    assert scored["sources"] == 1
    assert scored["cases"] == 3
    assert scored["native_error_cases"] == 2
    assert scored["biosure"] == {"exact_auto": 0, "incorrect_auto": 0, "abstentions": 3,
                                  "manual_review_records": 2}
    assert scored["direct_copy"] == {"exact_auto": 2, "incorrect_auto": 1, "abstentions": 0}
    assert scored["diff_review"]["manual_review_records"] == 2
    assert scored["learned_review"]["manual_review_records"] == 2


def test_scorer_rejects_switched_input_or_gold_identity():
    decisions = decide_inputs(_inputs(), MODEL)
    gold = _gold("0" * 64)
    with pytest.raises(ValueError, match="input digest"):
        score_decisions(decisions, gold)
    gold = _gold(decisions["input_sha256"])
    gold["cases"][1]["case_id"] = "switched"
    with pytest.raises(ValueError, match="case IDs"):
        score_decisions(decisions, gold)


def test_scorer_rejects_tampered_decision_output():
    decisions = decide_inputs(_inputs(), MODEL)
    decisions["cases"][1]["direct_copy"]["output_paragraphs"] = ["Tampered output."]
    with pytest.raises(ValueError, match="decision digest"):
        score_decisions(decisions, _gold(decisions["input_sha256"]))


def test_decide_cli_runs_without_a_gold_file(tmp_path):
    input_path = tmp_path / "inputs.json"
    output_path = tmp_path / "decisions.json"
    input_path.write_text(json.dumps(_inputs()), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_native_pilot.py"),
                             "decide", str(input_path), str(ROOT / "fixtures/ml_model.json"), str(output_path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert output_path.is_file()
    assert not (tmp_path / "gold.json").exists()


def test_native_excerpt_fixtures_have_separate_cc_by_rights_coverage():
    findings = _rights_metadata(ROOT, ["fixtures/native_pilot_inputs.json", "fixtures/native_pilot_gold.json"])
    assert findings == []


def test_frozen_native_pilot_result_is_recomputed_from_separate_gold():
    inputs = json.loads((ROOT / "fixtures/native_pilot_inputs.json").read_text(encoding="utf-8"))
    gold = json.loads((ROOT / "fixtures/native_pilot_gold.json").read_text(encoding="utf-8"))
    decisions = decide_inputs(inputs, MODEL)
    measured = score_decisions(decisions, gold)
    assert canonical_bytes(measured) == (ROOT / "results/native_pilot.json").read_bytes()


def test_offline_reproduction_reports_native_error_pilot_separately():
    measured = verify(ROOT)["native_pilot"]
    assert measured == {"sources": 1, "cases": 3, "native_error_cases": 2,
                        "biosure_exact_auto": 0, "biosure_incorrect_auto": 0,
                        "copy_exact_auto": 3, "copy_incorrect_auto": 0}


def test_no_prior_export_includes_pilot_scorecard_and_attributed_fixtures(tmp_path):
    destination = tmp_path / "public"
    manifest = prepare(ROOT, destination)
    assert manifest["cleared_for_public_release"] is True
    for relative in ("fixtures/native_pilot_inputs.json", "fixtures/native_pilot_gold.json",
                     "results/native_pilot.json", "report/public-scorecard.md"):
        assert (destination / relative).is_file()
