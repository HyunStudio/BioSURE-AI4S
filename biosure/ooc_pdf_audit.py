"""Recheck two frozen OoC publisher-PDF text-layer observations.

The source PDFs are acquired separately and are not packaged. This does not
verify visual gold, article truth, or reference authenticity.
"""

from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .pdf_extract import _normalise_lines


def extract_frozen_units(page_text: str, title_start: str, title_end: str,
                         abstract_start: str, abstract_end: str) -> tuple[str, str]:
    anchors = (title_start, title_end, abstract_start, abstract_end)
    if any(not isinstance(anchor, str) or not anchor or page_text.count(anchor) != 1 for anchor in anchors):
        raise ValueError("missing or ambiguous frozen page anchor")
    starts = [page_text.index(anchor) for anchor in anchors]
    if starts != sorted(starts) or len(set(starts)) != 4:
        raise ValueError("missing or ambiguous frozen page anchor order")
    title = page_text[starts[0]:starts[1]].strip()
    abstract = page_text[starts[2]:starts[3]].strip()
    if not title or not abstract:
        raise ValueError("empty frozen text unit")
    return title, abstract


def verify_frozen_pdf(pdf_bytes: bytes, inputs: dict) -> dict:
    source = inputs.get("source") if isinstance(inputs, dict) else None
    if not isinstance(source, dict) or not isinstance(pdf_bytes, bytes):
        raise ValueError("PDF and source metadata are required")
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    if digest != source.get("full_pdf_sha256"):
        raise ValueError("publisher PDF SHA-256 does not match frozen source")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise ValueError("publisher PDF page 1 is unavailable")
        page_text, _ = _normalise_lines(reader.pages[0].extract_text(extraction_mode="plain") or "")
    except (PdfReadError, KeyError, TypeError, RecursionError) as error:
        raise ValueError("publisher PDF text layer could not be read") from error
    anchors = source.get("page1_unit_anchors")
    if not isinstance(anchors, dict) or set(anchors) != {"title_start", "title_end", "abstract_start", "abstract_end"}:
        raise ValueError("frozen unit anchors are required")
    title, abstract = extract_frozen_units(page_text, **anchors)
    cases = inputs.get("cases")
    if not isinstance(cases, list) or len(cases) != 2:
        raise ValueError("two frozen cases are required")
    if cases[0].get("observed_paragraphs") != [title] or cases[1].get("observed_paragraphs") != [abstract]:
        raise ValueError("frozen observed units differ from publisher PDF text layer")
    return {"source_id": source["id"], "source_sha256": digest,
            "article_page": 1, "observed_cases_verified": 2, "gold_verified": False}
