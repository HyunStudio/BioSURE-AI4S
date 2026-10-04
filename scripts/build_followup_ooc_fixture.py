"""Build the two locked follow-up PDF-text/JATS fixtures from exact source bytes."""

from __future__ import annotations

import argparse
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.pdf_extract import _normalise_lines
from biosure.schema import canonical_bytes, sha256
from scripts.build_prospective_ooc_fixture import _authors, _gold, slice_unit


SOURCES = {
    "PMC12715219": {
        "doi": "10.1038/s41598-025-30612-2",
        "pdf_sha256": "686db248545986622ffbad23a00755040feff6d2c08e3ea6ccef9f8eb575090f",
        "xml_sha256": "93b2fb8126ec4beefd87f533418999b3935c758543ce3e325d07f8664c28fdba",
        "title": ("", " Delanyo Kpeglo1"),
        "abstract": ("Sally A. Peyman2 ", " Keywords Organ-on-a-chip"),
    },
    "PMC12707140": {
        "doi": "10.1128/iai.00346-25",
        "pdf_sha256": "b1ca79ae022e19e39ab4e3de22a78c8b9654ba51a6d668f7687b456234929942",
        "xml_sha256": "4834cd866442c80a3c2305fff62cf53a8885bf039d0906fc0290b17b97cf5f56",
        "title": ("Full-Length Text ", " Leslie A. Kirk,1"),
        "abstract": ("ABSTRACT ", " KEYWORDS gestational"),
    },
}


def build_one(source_dir: Path, source_id: str) -> tuple[dict, dict]:
    config = SOURCES[source_id]
    pdf_path, xml_path = (source_dir / f"{source_id}.{suffix}" for suffix in ("pdf", "xml"))
    pdf_bytes, xml_bytes = pdf_path.read_bytes(), xml_path.read_bytes()
    for suffix, content in (("pdf", pdf_bytes), ("xml", xml_bytes)):
        if hashlib.sha256(content).hexdigest() != config[f"{suffix}_sha256"]:
            raise ValueError(f"{source_id} {suffix} digest mismatch")
    reader = PdfReader(str(pdf_path), strict=True)
    if reader.is_encrypted or not reader.pages:
        raise ValueError(f"{source_id} article page one unavailable")
    page_text, _ = _normalise_lines(reader.pages[0].extract_text(extraction_mode="plain") or "")
    jats = ET.fromstring(xml_bytes)
    gold_units = {unit: _gold(jats.find(f".//{tag}"), unit)
                  for unit, tag in (("title", "article-title"), ("abstract", "abstract"))}
    source = {
        "id": source_id, "pmcid": source_id, "doi": config["doi"],
        "title": gold_units["title"], "authors": _authors(jats),
        "article_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{source_id}/",
        "pdf_source_url": f"https://pmc-oa-opendata.s3.amazonaws.com/{source_id}.1/{source_id}.1.pdf",
        "xml_source_url": f"https://pmc-oa-opendata.s3.amazonaws.com/{source_id}.1/{source_id}.1.xml",
        "pdf_sha256": config["pdf_sha256"], "xml_sha256": config["xml_sha256"],
        "license_uri": "https://creativecommons.org/licenses/by/4.0/",
        "change_notice": "Short selected title/abstract PDF text-layer and continuous JATS excerpts are NFKC/whitespace-normalized; no full PDF, XML or figure redistributed.",
        "selection": "Metadata-only lock at commit 1e42433 on 2026-10-04 before selected PDF/XML content inspection; article-page-one full title and abstract attempted.",
        "extractor": "pypdf 6.19.0 plain; frozen BioSURE _normalise_lines; exact unique source anchors in builder",
        "article_page": 1,
    }
    cases, answers = [], []
    for unit in ("title", "abstract"):
        observed = slice_unit(page_text, *config[unit])
        expected = gold_units[unit]
        case_id = f"{source_id}-{unit}"
        cases.append({"case_id": case_id, "source_locator": f"deposited PDF article page 1 full {unit}",
                      "condition": "control" if observed == expected else "native_extraction_error",
                      "reference_paragraphs": [expected], "observed_paragraphs": [observed]})
        answers.append({"case_id": case_id, "gold_paragraphs": [expected],
                        "defect_note": "Observed-versus-JATS discrepancy may include typography and reflow, not only PDF-parser faults."})
    inputs = {"schema_version": "biosure.native-pilot-inputs/1.0", "source": source, "cases": cases}
    gold = {"schema_version": "biosure.native-pilot-gold/1.0", "input_sha256": sha256(inputs),
            "adjudication": "Continuous same-article JATS with one development agent's visual page-one title/abstract boundary check; no independent expert or full line-by-line transcription.",
            "cases": answers}
    return inputs, gold


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--source-id", required=True, choices=tuple(SOURCES))
    parser.add_argument("--out-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        inputs, gold = build_one(args.source_dir, args.source_id)
        prefix = args.out_root / "fixtures" / f"followup_ooc_{args.source_id}"
        paths = (prefix.with_name(prefix.name + "_inputs.json"), prefix.with_name(prefix.name + "_gold.json"))
        if any(path.exists() for path in paths):
            raise ValueError("fixture output already exists")
        for path, value in zip(paths, (inputs, gold)):
            path.write_bytes(canonical_bytes(value))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
