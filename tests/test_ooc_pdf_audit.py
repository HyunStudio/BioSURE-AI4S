"""Frozen, same-input OoC publisher-PDF audit contracts."""

from pathlib import Path

import pytest

from biosure.native_pilot import decide_inputs, score_decisions
from biosure.ooc_pdf_audit import extract_frozen_units, verify_frozen_pdf
from biosure.schema import loads_json
from scripts.verify_reproduction import verify


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("pmcid", ["PMC5562747", "PMC7170869"])
def test_frozen_ooc_decisions_replay_without_pdf_or_gold(pmcid):
    inputs = loads_json((ROOT / f"fixtures/ooc_pdf_{pmcid}_inputs.json").read_text(encoding="utf-8"))
    gold = loads_json((ROOT / f"fixtures/ooc_pdf_{pmcid}_gold.json").read_text(encoding="utf-8"))
    model = loads_json((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    frozen = loads_json((ROOT / f"results/ooc_pdf_{pmcid}.json").read_text(encoding="utf-8"))
    assert [case["source_locator"] for case in inputs["cases"]] == [
        "Publisher PDF article page 1 full title", "Publisher PDF article page 1 full abstract"
    ]
    decisions = decide_inputs(inputs, model)
    assert score_decisions(decisions, gold) == frozen
    assert frozen["cases"] == 2
    assert frozen["native_error_cases"] == {"PMC5562747": 0, "PMC7170869": 2}[pmcid]
    assert [case["condition"] for case in inputs["cases"]] == (
        ["control", "control"] if pmcid == "PMC5562747" else
        ["native_extraction_error", "native_extraction_error"]
    )
    assert frozen["biosure"]["incorrect_auto"] == 0


def test_frozen_unit_extraction_fails_on_missing_or_ambiguous_anchors():
    with pytest.raises(ValueError, match="missing or ambiguous"):
        extract_frozen_units("title A title B abstract end", "title", "abstract", "abstract", "end")


def test_frozen_unit_extraction_keeps_both_complete_units():
    page = "header Title changed word Authors text Abstract damaged token Introduction"
    assert extract_frozen_units(page, "Title", " Authors", "Abstract", " Introduction") == (
        "Title changed word", "Abstract damaged token"
    )


def test_pdf_verification_rejects_wrong_bytes():
    inputs = loads_json((ROOT / "fixtures/ooc_pdf_PMC5562747_inputs.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="SHA-256"):
        verify_frozen_pdf(b"%PDF-fake", inputs)


def test_offline_reproduction_separates_controls_from_pdf_errors():
    measured = verify(ROOT)["ooc_pdf_audit"]
    assert measured == {
        "sources": 2, "attempted_units": 4, "native_error_units": 2,
        "biosure_exact_auto": 0, "biosure_incorrect_auto": 0,
        "biosure_abstentions": 4, "copy_exact_auto": 4,
        "diff_review_records": 2, "learned_lexical_alert_records": 0,
    }
