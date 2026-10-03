"""Pilot decisions must be gold-blind and expose bad-reference copy risk."""

import json
import hashlib
import io
import subprocess
import sys
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from biosure import native_pilot
from biosure.native_pilot import decide_inputs, score_decisions
from biosure.schema import canonical_bytes, sha256
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
                      {"case_id": "false-reference", "gold_paragraphs": ["A verified claim."]}]}


def test_decision_phase_needs_no_gold_and_compares_identical_records():
    decisions = decide_inputs(_inputs(), MODEL)
    assert [item["case_id"] for item in decisions["cases"]] == ["unchanged", "spacing", "false-reference"]
    assert all(set(item) == {"case_id", "condition", "observed_paragraphs", "biosure", "direct_copy", "diff_review", "learned_review"}
               for item in decisions["cases"])
    assert decisions["cases"][1]["biosure"]["action"] == "ABSTAIN"
    assert decisions["cases"][1]["direct_copy"]["output_paragraphs"] == ["A reference sentence."]
    assert decisions["cases"][1]["diff_review"]["action"] == "REVIEW"
    assert "action" not in decisions["cases"][1]["learned_review"]
    assert decisions["cases"][1]["learned_review"]["correspondences"][0]["above_threshold"] is False
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
    assert scored["learned_review"] == {"native_error_cases_with_lexical_alerts": 0,
                                           "native_error_cases_below_match_threshold": 2,
                                           "automatic_repairs": 0}


def _two_page_pdf(first: str, second: str) -> bytes:
    stream = io.BytesIO()
    writer = canvas.Canvas(stream)
    writer.drawString(72, 700, first)
    writer.showPage()
    writer.drawString(72, 700, second)
    writer.save()
    return stream.getvalue()


def test_native_source_verifier_maps_full_pdf_cover_to_article_page():
    assert hasattr(native_pilot, "verify_native_pdf_source")
    pdf = _two_page_pdf("Repository cover", "A heading.")
    inputs = _inputs()
    inputs["source"]["full_pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
    inputs["source"]["pdf_excerpt_sha256"] = "0" * 64
    inputs["cases"] = inputs["cases"][:1]
    assert native_pilot.verify_native_pdf_source(pdf, inputs) == {
        "source_format": "full_pdf_with_cover", "source_sha256": hashlib.sha256(pdf).hexdigest(),
        "article_page": 2, "observed_cases_verified": 1, "gold_verified": False}


def test_native_source_verifier_rejects_wrong_pdf_and_unobserved_text():
    assert hasattr(native_pilot, "verify_native_pdf_source")
    pdf = _two_page_pdf("Something else", "Another page")
    inputs = _inputs()
    inputs["source"]["full_pdf_sha256"] = "0" * 64
    inputs["source"]["pdf_excerpt_sha256"] = hashlib.sha256(pdf).hexdigest()
    inputs["cases"] = inputs["cases"][:1]
    with pytest.raises(ValueError, match="not found"):
        native_pilot.verify_native_pdf_source(pdf, inputs)
    inputs["source"]["pdf_excerpt_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        native_pilot.verify_native_pdf_source(pdf, inputs)


def test_native_source_cli_verifies_pdf_without_gold(tmp_path):
    pdf = _two_page_pdf("A heading.", "Another page")
    inputs = _inputs()
    inputs["source"]["full_pdf_sha256"] = "0" * 64
    inputs["source"]["pdf_excerpt_sha256"] = hashlib.sha256(pdf).hexdigest()
    inputs["cases"] = inputs["cases"][:1]
    pdf_path = tmp_path / "excerpt.pdf"
    inputs_path = tmp_path / "inputs.json"
    pdf_path.write_bytes(pdf)
    inputs_path.write_text(json.dumps(inputs), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/verify_native_source.py"),
                             str(pdf_path), str(inputs_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["observed_cases_verified"] == 1
    assert json.loads(result.stdout)["gold_verified"] is False


def test_scorer_rejects_switched_input_or_gold_identity():
    decisions = decide_inputs(_inputs(), MODEL)
    gold = _gold("0" * 64)
    with pytest.raises(ValueError, match="input digest"):
        score_decisions(decisions, gold)
    gold = _gold(decisions["input_sha256"])
    gold["cases"][1]["case_id"] = "switched"
    with pytest.raises(ValueError, match="case IDs"):
        score_decisions(decisions, gold)


@pytest.mark.parametrize("case_index,wrong_condition", [(0, "native_extraction_error"), (1, "control")])
def test_scorer_rejects_condition_that_disagrees_with_observed_and_gold(case_index, wrong_condition):
    inputs = _inputs()
    inputs["cases"][case_index]["condition"] = wrong_condition
    decisions = decide_inputs(inputs, MODEL)
    with pytest.raises(ValueError, match="condition disagrees"):
        score_decisions(decisions, _gold(decisions["input_sha256"]))


def test_scorer_rejects_unknown_condition_even_with_recomputed_digest():
    decisions = decide_inputs(_inputs(), MODEL)
    decisions["cases"][1]["condition"] = "unclassified"
    decisions["decision_sha256"] = sha256({key: value for key, value in decisions.items()
                                           if key != "decision_sha256"})
    with pytest.raises(ValueError, match="invalid pilot condition"):
        score_decisions(decisions, _gold(decisions["input_sha256"]))


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
                     "results/native_pilot.json", "report/public-scorecard.md",
                     "scripts/verify_native_source.py"):
        assert (destination / relative).is_file()
