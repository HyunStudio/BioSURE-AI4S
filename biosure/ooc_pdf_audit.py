"""Recheck frozen OoC publisher-PDF text-layer observations.

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
    if any(not isinstance(anchor, str) or not anchor for anchor in
           (title_start, title_end, abstract_start, abstract_end)):
        raise ValueError("missing or ambiguous frozen page anchor")
    title = extract_frozen_title(page_text, title_start, title_end)
    if page_text.count(abstract_end) != 1:
        raise ValueError("missing or ambiguous frozen page anchor")
    after_title = page_text.index(title_end) + len(title_end)
    abstract_limit = page_text.index(abstract_end)
    if after_title >= abstract_limit:
        raise ValueError("missing or ambiguous frozen page anchor order")
    region = page_text[after_title:abstract_limit]
    if region.count(abstract_start) != 1:
        raise ValueError("missing or ambiguous frozen page anchor")
    abstract = region[region.index(abstract_start):].strip()
    if not abstract:
        raise ValueError("empty frozen text unit")
    return title, abstract


def extract_frozen_title(page_text: str, title_start: str, title_end: str) -> str:
    """Use the title occurrence nearest its unique author boundary."""
    if any(not isinstance(anchor, str) or not anchor for anchor in (title_start, title_end)):
        raise ValueError("missing or ambiguous frozen page anchor")
    if page_text.count(title_end) != 1:
        raise ValueError("missing or ambiguous frozen page anchor")
    end = page_text.index(title_end)
    before_end = page_text[:end]
    start = before_end.rfind(title_start)
    if start < 0:
        raise ValueError("missing or ambiguous frozen page anchor")
    title = before_end[start:].strip()
    if not title:
        raise ValueError("empty frozen text unit")
    return title


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
    if not isinstance(anchors, dict) or set(anchors) not in (
            {"title_start", "title_end"},
            {"title_start", "title_end", "abstract_start", "abstract_end"}):
        raise ValueError("frozen unit anchors are required")
    cases = inputs.get("cases")
    title_only = set(anchors) == {"title_start", "title_end"}
    if not isinstance(cases, list) or len(cases) != (1 if title_only else 2):
        raise ValueError("frozen case count disagrees with unit anchors")
    units = ([extract_frozen_title(page_text, **anchors)] if title_only else
             list(extract_frozen_units(page_text, **anchors)))
    if any(not isinstance(case, dict) or case.get("observed_paragraphs") != [unit]
           for case, unit in zip(cases, units)):
        raise ValueError("frozen observed units differ from publisher PDF text layer")
    return {"source_id": source["id"], "source_sha256": digest,
            "article_page": 1, "observed_cases_verified": len(units), "gold_verified": False}
