"""Build the locked 2026-10-03 PDF audit from separately acquired PMC Cloud files.

The PDFs and XML are inputs, not redistributed. This script is not a visual
adjudicator: an operator must compare JATS gold with rendered publisher pages.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.native_pilot import decide_inputs, score_decisions
from biosure.ooc_pdf_audit import extract_frozen_title, extract_frozen_units, verify_frozen_pdf
from biosure.pdf_extract import _normalise_lines
from biosure.schema import canonical_bytes, loads_json, sha256


SOURCES = (
    {"pmcid": "PMC12078732", "doi": "10.1038/s41378-025-00933-3",
     "article_url": "https://www.nature.com/articles/s41378-025-00933-3",
     "pdf_sha256": "25b81578b16529bc390a74e9ea3d9b371967a53f463f5bac8ee570603be06139",
     "xml_sha256": "3bde0cf965cca88939976d44483d2416ab9c6e685fc168fd1879abea4ab99f78",
     "anchors": {"title_start": "An eighteen-organ", "title_end": " Jing Wang 1",
                 "abstract_start": "Physiological supporting", "abstract_end": " Introduction"},
     "notes": ("The text layer spaces the final title phrase as 'f o rd r u gd i s c o v e r y'.",
               "The text layer splits the visible word 'efficiency' as 'ef ficiency'.")},
    {"pmcid": "PMC12300027", "doi": "10.3390/mi16070740",
     "article_url": "https://www.mdpi.com/2072-666X/16/7/740",
     "pdf_sha256": "a7a4e44a5e8f1821ea3992b9b8007ded38d6393bb828274288b9077e226d972b",
     "xml_sha256": "2296c790e995fbf59eaa8e3eb8e6c140706419f3a0648d27129e0174ce92e72b",
     "anchors": {"title_start": "An Organ-on-a-Chip Modular Platform", "title_end": " Anastasia Kanioura 1",
                 "abstract_start": "OoC systems employing", "abstract_end": " Keywords:"},
     "notes": ("Control: article title matches the rendered page and JATS.",
               "The visible page has discretionary line-wrap hyphens in 'faith-fully' and 'de-tection'; "
               "JATS has 'faithfully' and 'detection'. This is a canonical reflow discrepancy, "
               "not a claim that pypdf hallucinated glyphs.")},
    {"pmcid": "PMC12158725", "doi": "10.3389/fonc.2025.1602225",
     "article_url": "https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2025.1602225/full",
     "pdf_sha256": "ff5a61edea83e9928ae2831275daf3cb6006c233ca5df78aae8776fc5be41d3a",
     "xml_sha256": "a812f5e6c7401eb0f9fa708ed8333eb65c80146778460bebe235e6103635b6b2",
     "anchors": {"title_start": "Leaf-vein-inspired multi-organ", "title_end": " Liuyin Liu 1"},
     "notes": ("Control: article title matches the rendered page and JATS.",)},
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gold_text(element: ET.Element) -> str:
    return " ".join(unicodedata.normalize("NFKC", "".join(element.itertext())).split())


def build(source_dir: Path, package_root: Path) -> dict:
    model = loads_json((package_root / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    totals = {"schema_version": "biosure.three-source-pdf-audit/1.0", "sources": 0,
              "attempted_units": 6, "scorable_units": 0, "observed_reference_discrepancy_units": 0,
              "biosure_exact_auto": 0, "biosure_incorrect_auto": 0, "biosure_abstentions": 0,
              "copy_exact_auto": 0, "copy_incorrect_auto": 0,
              "diff_review_records": 0, "learned_lexical_alert_records": 0,
              "unscorable_units": [{"case_id": "PMC12158725-abstract",
                                    "reason": "complete abstract extends beyond article page 1"}],
              "scope": "Three internally preselected CC BY sources; JATS/rendered-page one-agent gold, "
                       "no independent adjudication or timed user comparison."}
    for config in SOURCES:
        pmcid = config["pmcid"]
        pdf_bytes = (source_dir / f"{pmcid}.pdf").read_bytes()
        xml_bytes = (source_dir / f"{pmcid}.xml").read_bytes()
        if _digest(pdf_bytes) != config["pdf_sha256"] or _digest(xml_bytes) != config["xml_sha256"]:
            raise ValueError(pmcid + " PDF/XML digest mismatch")
        root = ET.fromstring(xml_bytes)
        title_element = root.find(".//article-title")
        abstract_element = root.find(".//abstract")
        if title_element is None or abstract_element is None:
            raise ValueError(pmcid + " lacks title or abstract in JATS")
        gold_units = [_gold_text(title_element), _gold_text(abstract_element)]
        reader = PdfReader(str(source_dir / f"{pmcid}.pdf"), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError(pmcid + " page 1 unavailable")
        page_text, _ = _normalise_lines(reader.pages[0].extract_text(extraction_mode="plain") or "")
        anchors = config["anchors"]
        observed_units = ([extract_frozen_title(page_text, **anchors)] if pmcid == "PMC12158725" else
                          list(extract_frozen_units(page_text, **anchors)))
        source = {"id": pmcid + "-pmc-cloud-pdf-page1", "title": gold_units[0],
                  "doi": config["doi"], "pmcid": pmcid, "article_url": config["article_url"],
                  "full_pdf_source_url": f"https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.1/{pmcid}.1.pdf",
                  "xml_source_url": f"https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.1/{pmcid}.1.xml",
                  "license_uri": "https://creativecommons.org/licenses/by/4.0/",
                  "full_pdf_sha256": config["pdf_sha256"], "xml_sha256": config["xml_sha256"],
                  "extractor": "pypdf 6.16.2 plain, then _normalise_lines (NFKC, preserved line-end hyphens, whitespace)",
                  "selection": "Locked 2026-10-03 before PDF text inspection; complete article-page-1 title/abstract "
                               "attempted, Frontiers abstract unscorable because it extends to page 2.",
                  "page1_unit_anchors": anchors}
        cases = []
        answers = []
        for index, observed in enumerate(observed_units):
            unit = ("title", "abstract")[index]
            gold_text = gold_units[index]
            case_id = f"{pmcid}-{unit}"
            cases.append({"case_id": case_id,
                          "source_locator": "PMC Cloud deposited PDF article page 1 full " + unit,
                          "condition": "control" if observed == gold_text else "native_extraction_error",
                          "reference_paragraphs": [gold_text], "observed_paragraphs": [observed]})
            answers.append({"case_id": case_id, "gold_paragraphs": [gold_text],
                            "defect_note": config["notes"][index]})
        inputs = {"schema_version": "biosure.native-pilot-inputs/1.0", "source": source, "cases": cases}
        gold = {"schema_version": "biosure.native-pilot-gold/1.0", "input_sha256": sha256(inputs),
                "adjudication": "PMC Cloud JATS canonical text was checked by one development agent against "
                                "the rendered deposited PDF page 1; no independent expert gold or established "
                                "byte identity with each publisher-hosted PDF.",
                "cases": answers}
        verified = verify_frozen_pdf(pdf_bytes, inputs)
        if verified["observed_cases_verified"] != len(cases):
            raise ValueError(pmcid + " observed PDF unit count mismatch")
        scored = score_decisions(decide_inputs(inputs, model), gold)
        for suffix, data in (("inputs", inputs), ("gold", gold)):
            (package_root / "fixtures" / f"ooc_pdf_{pmcid}_{suffix}.json").write_bytes(canonical_bytes(data))
        (package_root / "results" / f"ooc_pdf_{pmcid}.json").write_bytes(canonical_bytes(scored))
        totals["sources"] += 1
        totals["scorable_units"] += scored["cases"]
        totals["observed_reference_discrepancy_units"] += scored["native_error_cases"]
        totals["biosure_exact_auto"] += scored["biosure"]["exact_auto"]
        totals["biosure_incorrect_auto"] += scored["biosure"]["incorrect_auto"]
        totals["biosure_abstentions"] += scored["biosure"]["abstentions"]
        totals["copy_exact_auto"] += scored["direct_copy"]["exact_auto"]
        totals["copy_incorrect_auto"] += scored["direct_copy"]["incorrect_auto"]
        totals["diff_review_records"] += scored["diff_review"]["manual_review_records"]
        totals["learned_lexical_alert_records"] += scored["learned_review"]["native_error_cases_with_lexical_alerts"]
    (package_root / "results/three_source_pdf_audit.json").write_bytes(canonical_bytes(totals))
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="Directory containing the three PMC<id>.pdf/.xml source pairs")
    parser.add_argument("package_root", type=Path, nargs="?", default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(build(args.source_dir, args.package_root))


if __name__ == "__main__":
    main()
