"""Frozen, same-input OoC publisher-PDF audit contracts."""

import hashlib
import io
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

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


def test_frozen_unit_extraction_allows_repeated_title_in_later_citation():
    page = "Title words Author Name Abstract words Keywords: citation Title words"
    assert extract_frozen_units(page, "Title words", " Author Name", "Abstract words", " Keywords:") == (
        "Title words", "Abstract words"
    )


def test_frozen_unit_extraction_uses_title_nearest_author_boundary_after_front_matter_citation():
    page = "Citation Title words journal Article Title words Author Name Abstract words Keywords:"
    assert extract_frozen_units(page, "Title words", " Author Name", "Abstract words", " Keywords:") == (
        "Title words", "Abstract words"
    )


def test_pdf_verification_rejects_wrong_bytes():
    inputs = loads_json((ROOT / "fixtures/ooc_pdf_PMC5562747_inputs.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="SHA-256"):
        verify_frozen_pdf(b"%PDF-fake", inputs)


def test_pdf_verification_accepts_predeclared_title_only_when_abstract_spills_to_page_2():
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 700, "Article title words")
    pdf.drawString(72, 680, "Author Name")
    pdf.save()
    document = stream.getvalue()
    inputs = {"source": {"id": "title-only", "full_pdf_sha256": hashlib.sha256(document).hexdigest(),
                         "page1_unit_anchors": {"title_start": "Article title", "title_end": " Author Name"}},
              "cases": [{"case_id": "title", "observed_paragraphs": ["Article title words"]}]}
    assert verify_frozen_pdf(document, inputs)["observed_cases_verified"] == 1


def test_offline_reproduction_separates_controls_from_pdf_errors():
    measured = verify(ROOT)["ooc_pdf_audit"]
    assert measured == {
        "sources": 2, "attempted_units": 4, "native_error_units": 2,
        "biosure_exact_auto": 0, "biosure_incorrect_auto": 0,
        "biosure_abstentions": 4, "copy_exact_auto": 4,
        "diff_review_records": 2, "learned_lexical_alert_records": 0,
    }


def test_three_new_sources_replay_with_one_predeclared_unscorable_abstract():
    model = loads_json((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    for pmcid, case_count in (("PMC12078732", 2), ("PMC12300027", 2), ("PMC12158725", 1)):
        inputs = loads_json((ROOT / f"fixtures/ooc_pdf_{pmcid}_inputs.json").read_text(encoding="utf-8"))
        gold = loads_json((ROOT / f"fixtures/ooc_pdf_{pmcid}_gold.json").read_text(encoding="utf-8"))
        result = loads_json((ROOT / f"results/ooc_pdf_{pmcid}.json").read_text(encoding="utf-8"))
        assert len(inputs["cases"]) == case_count
        assert score_decisions(decide_inputs(inputs, model), gold) == result
    summary = loads_json((ROOT / "results/three_source_pdf_audit.json").read_text(encoding="utf-8"))
    assert summary["sources"] == 3
    assert summary["attempted_units"] == 6
    assert summary["scorable_units"] == 5
    assert summary["unscorable_units"] == [
        {"case_id": "PMC12158725-abstract", "reason": "complete abstract extends beyond article page 1"}
    ]
    assert verify(ROOT)["three_source_pdf_audit"] == summary
