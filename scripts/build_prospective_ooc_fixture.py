"""Build fixed prospectively selected OoC PDF fixtures from exact source bytes."""

from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.pdf_extract import _normalise_lines
from biosure.schema import canonical_bytes, sha256


SOURCES = {
    "PMC12624441": {
        "doi": "10.1021/acsptsci.5c00554",
        "pdf_sha256": "1f0e2d7a3c20fa88e5e255402eb6c4f6ef4d8a57b4b7907998dfacd9f28c8c36",
        "xml_sha256": "09f1a3e6fe66033926ae7b1b0872c3107efb0aa8c0aa395cf78be635cefc390c",
        "title": ("", " Chander K. Negi"),
        "abstract": ("ABSTRACT: ", " KEYWORDS:"),
    },
    "PMC12864593": {
        "doi": "10.1002/adhm.202502711",
        "pdf_sha256": "3dbcd0aadde0f27c8daa6b8de4a40e13c68daee61d19c97db4f6a58ada2d5833",
        "xml_sha256": "a3c1658c7444de70a9a799da312773bcccc8e44a3c57e170e380acd719834027",
        "title": ("www.advhealthmat.de ", " Seunggyu Kim"),
        "abstract": ("Roger D. Kamm* ", " S.Kim,E.C.K"),
    },
    "PMC12850162": {
        "doi": "10.1002/smsc.202500154",
        "pdf_sha256": "79b9b7c1024a547dd28fe27a7fcaa133574a5f08bef53fd3c702ef6d90d26065",
        "xml_sha256": "27cf28af94fe6fa43553513edb11c2ee2dc4d3816857ed8e18ff30d5a6c452af",
        "title": ("", " Su Liu"),
        "abstract": ("DOI: 10.1002/smsc.202500154 ", " REVIEW www.small-science-journal.com"),
    },
    "PMC12838518": {
        "doi": "10.3390/bioengineering13010009",
        "pdf_sha256": "754df75b0789e8f41651941adac72db20e97a8d08ed44059022e7f21a111426e",
        "xml_sha256": "34a71b8329bd22018d7997abf7b64ee9fb51e20a8104f5c4e8e5812cef07ba3b",
        "title": ("Review ", " Megan Moore"),
        "abstract": ("Abstract ", " Keywords:"),
    },
    "PMC12838946": {
        "doi": "10.3390/biomimetics11010018",
        "pdf_sha256": "2dd6dc05a7358e5120d37204102186eaa33e5006eb04d72fb531b0a954deb36a",
        "xml_sha256": "7763cf0d6529426d788ed0fff4cd0aa475ccde309db57e0467f056c89afe33b7",
        "title": ("Review ", " Daniele Marazzi"),
        "abstract": ("Abstract ", " Keywords:"),
    },
    "PMC12789962": {
        "doi": "10.1002/adbi.202500225",
        "pdf_sha256": "3a19f888b0bb7cabb5c43f74c512e7830bc3196a8977d3efb815812cd0cee080",
        "xml_sha256": "bfa112218cfd2efdedaa498e10a9960e2d4e4bdaeda02326cc56d160c5ee46c3",
        "title": ("www.advanced-bio.com ", " Bokyong Kim"),
        "abstract": ("Young-Jae Cho* ", " B.Kim,J.Kim"),
    },
    "PMC12755145": {
        "doi": "10.1186/s40486-025-00246-0",
        "pdf_sha256": "26ed18872f6e8aca23ea6a30b7da3585ef21c31934035bc6aebd13de9272fb8a",
        "xml_sha256": "61b0d3cb16b0519dbbb6accc1fd4c4beba70233dace4d49d35fb323d7e620099",
        "title": ("Keywords Microphysiological system, Organ-on-chip, High throughput assay, Automation ", " Po Yi Lam"),
        "abstract": ("Abstract ", " Keywords Microphysiological"),
    },
    "PMC12732092": {
        "doi": "10.3390/cells14241986",
        "pdf_sha256": "0c5dbf4ca6108ae5a3fd31d6e3db30ee9144de194efb7190dcc8f90503f77f73",
        "xml_sha256": "5602e646c6af0f0aef57860289e57d359e5453101c1a1b5c9edf70b304d15dc2",
        "title": ("Review ", " Giorgia Lombardozzi"),
        "abstract": ("Abstract ", " Keywords:"),
    },
}


def slice_unit(text: str, start: str, end: str) -> str:
    if (start and text.count(start) != 1) or text.count(end) != 1:
        raise ValueError("source unit anchors must be unique")
    first = text.index(start) + len(start) if start else 0
    last = text.index(end, first)
    if first >= last:
        raise ValueError("source unit anchors must be in order")
    return text[first:last]


def _gold(element: ET.Element | None, unit: str) -> str:
    if element is None:
        raise ValueError("JATS lacks " + unit)
    if unit == "abstract":
        pieces = []
        for child in element:
            if child.tag == "p":
                pieces.append("".join(child.itertext()))
            elif child.tag == "title":
                continue
            elif child.tag == "sec" and (child.findtext("title") or "").strip() == "Supplementary Information":
                continue
            else:
                raise ValueError("unhandled abstract structure")
        raw = " ".join(pieces)
    else:
        raw = "".join(element.itertext())
    text = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not text:
        raise ValueError("JATS has empty " + unit)
    return text


def _authors(jats: ET.Element) -> list[str]:
    authors = []
    for contributor in jats.findall(".//article-meta/contrib-group/contrib"):
        if contributor.get("contrib-type") != "author":
            continue
        name = contributor.find("name")
        if name is None:
            continue
        parts = []
        for tag in ("given-names", "surname"):
            item = name.find(tag)
            if item is not None:
                parts.append(" ".join("".join(item.itertext()).split()))
        if parts:
            authors.append(" ".join(parts))
    if not authors:
        raise ValueError("JATS lacks named authors")
    return authors


def build_one(source_dir: Path, source_id: str) -> tuple[dict, dict]:
    config = SOURCES[source_id]
    pdf_path = source_dir / (source_id + ".pdf")
    xml_path = source_dir / (source_id + ".xml")
    pdf_bytes, xml_bytes = pdf_path.read_bytes(), xml_path.read_bytes()
    if hashlib.sha256(pdf_bytes).hexdigest() != config["pdf_sha256"]:
        raise ValueError(source_id + " PDF digest mismatch")
    if hashlib.sha256(xml_bytes).hexdigest() != config["xml_sha256"]:
        raise ValueError(source_id + " XML digest mismatch")
    reader = PdfReader(str(pdf_path), strict=True)
    if reader.is_encrypted or not reader.pages:
        raise ValueError(source_id + " article page 1 unavailable")
    page_text, _ = _normalise_lines(reader.pages[0].extract_text(extraction_mode="plain") or "")
    jats = ET.fromstring(xml_bytes)
    gold_units = {"title": _gold(jats.find(".//article-title"), "title"),
                  "abstract": _gold(jats.find(".//abstract"), "abstract")}
    source = {"id": source_id, "pmcid": source_id, "doi": config["doi"],
              "title": gold_units["title"], "authors": _authors(jats),
              "article_url": "https://pmc.ncbi.nlm.nih.gov/articles/" + source_id + "/",
              "pdf_source_url": "https://pmc-oa-opendata.s3.amazonaws.com/" + source_id + ".1/" + source_id + ".1.pdf",
              "xml_source_url": "https://pmc-oa-opendata.s3.amazonaws.com/" + source_id + ".1/" + source_id + ".1.xml",
              "pdf_sha256": config["pdf_sha256"], "xml_sha256": config["xml_sha256"],
              "license_uri": "https://creativecommons.org/licenses/by/4.0/",
              "change_notice": "Short selected title/abstract text-layer and canonical JATS excerpts are NFKC/whitespace-normalized for comparison; no full PDF, XML or figures redistributed.",
              "selection": "Locked 2026-10-04 before selected PDF text-layer inspection; complete article-page-1 title and abstract attempted.",
              "extractor": "pypdf 6.19.0 plain; BioSURE _normalise_lines; exact unique anchors recorded in builder",
              "article_page": 1}
    cases, answers = [], []
    for unit in ("title", "abstract"):
        observed = slice_unit(page_text, *config[unit])
        expected = gold_units[unit]
        case_id = source_id + "-" + unit
        cases.append({"case_id": case_id,
                      "source_locator": "deposited PDF article page 1 full " + unit,
                      "condition": "control" if observed == expected else "native_extraction_error",
                      "reference_paragraphs": [expected], "observed_paragraphs": [observed]})
        answers.append({"case_id": case_id, "gold_paragraphs": [expected],
                        "defect_note": "Observed-versus-canonical discrepancy may include layout reflow, not only PDF-parser faults."})
    inputs = {"schema_version": "biosure.native-pilot-inputs/1.0", "source": source, "cases": cases}
    gold = {"schema_version": "biosure.native-pilot-gold/1.0", "input_sha256": sha256(inputs),
            "adjudication": "Canonical JATS with one development agent's visual title/abstract boundary check of the rendered deposited page; no independent expert or full line-by-line transcription.",
            "cases": answers}
    return inputs, gold


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--source-id", required=True, choices=sorted(SOURCES))
    parser.add_argument("--out-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        inputs, gold = build_one(args.source_dir, args.source_id)
        prefix = args.out_root / "fixtures" / ("prospective_ooc_" + args.source_id)
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
