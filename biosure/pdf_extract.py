"""Conservative PDF text-layer import. Segmentation/layout are *not* verified.

pypdf is BSD-3-Clause. Extraction stays local and in memory; figure image text
is not OCRed. Page-text chunks are a starting point for manual correction, not
authenticated paragraphs or safe input to automatic repair without review.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_PAGES = 32
MAX_TEXT_CHARS = 262_144
MAX_CHUNK_CHARS = 4000


def _spacing_artifacts(text: str) -> bool:
    # PDFs with individually positioned glyphs can look readable while whole
    # scientific words are fractured into one-character tokens.
    return bool(re.search(r'(?:\b[A-Za-z]\s+){6,}', text))


def _normalise_lines(value: str) -> tuple[str, bool]:
    value = unicodedata.normalize('NFKC', value)
    lines = [part.strip() for part in value.splitlines() if part.strip()]
    joined = any(line.endswith('-') for line in lines[:-1])
    text = '\n'.join(lines)
    # The hyphen may be part of a scientific compound (organ-on-a-chip).
    # Preserve its glyph; a reviewer must resolve optional line-wrap hyphens.
    text = re.sub(r'(?<=\w)-\n(?=\w)', '-', text)
    text = re.sub(r'\s*\n\s*', ' ', text)
    return re.sub(r'\s+', ' ', text).strip(), joined


def _chunks(raw: str) -> tuple[list[str], bool]:
    """Bound text chunks without inventing paragraph breaks."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return [], False
    groups = []
    current = []
    for line in lines:
        if len(line) > MAX_CHUNK_CHARS:
            raise ValueError('A PDF text line exceeds the 4000-character chunk limit')
        tentative = '\n'.join(current + [line])
        if current and len(tentative) > MAX_CHUNK_CHARS:
            groups.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append('\n'.join(current))
    return groups, len(groups) > 1


def extract_pdf(data: bytes) -> dict:
    """Return review-only page text chunks with page and content-hash provenance."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_PDF_BYTES:
        raise ValueError('PDF must be non-empty and at most 16 MiB')
    if not data.startswith(b'%PDF-'):
        raise ValueError('Not a PDF file')
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported')
        count = len(reader.pages)
        if not 0 < count <= MAX_PAGES:
            raise ValueError('PDF must contain 1 to 32 pages')
        paragraphs = []
        warnings = {'READING_ORDER_REQUIRES_REVIEW', 'PARAGRAPH_BOUNDARIES_REQUIRE_REVIEW'}
        image_count = 0
        for number, page in enumerate(reader.pages, start=1):
            images = len(page.images)
            image_count += images
            if images:
                warnings.add('IMAGE_TEXT_NOT_EXTRACTED')
            raw = page.extract_text(extraction_mode='plain') or ''
            if _spacing_artifacts(raw):
                warnings.add('TEXT_SPACING_ARTIFACTS')
            groups, split = _chunks(raw)
            if not groups:
                warnings.add('NO_TEXT_LAYER')
            if split:
                warnings.add('PAGE_CHUNK_BOUNDARY_REQUIRES_REVIEW')
            for group in groups:
                text, line_end_hyphen = _normalise_lines(group)
                if line_end_hyphen:
                    warnings.add('LINE_END_HYPHEN_REQUIRES_REVIEW')
                paragraphs.append({'page': number, 'bbox': None,
                                   'column': 'unverified', 'text': text})
        if len(paragraphs) > 128:
            raise ValueError('PDF produced more than 128 text chunks; select fewer pages')
        text = '\n\n'.join(item['text'] for item in paragraphs)
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError('Extracted text is too long; select a shorter PDF')
        return {'pages': count, 'image_count': image_count,
                'paragraphs': paragraphs, 'warnings': sorted(warnings),
                'review_required': True,
                'segmentation': 'page_text_chunks_unverified',
                'source_pdf_sha256': hashlib.sha256(data).hexdigest(),
                'extracted_text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
    except (PdfReadError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Could not read PDF') from error
