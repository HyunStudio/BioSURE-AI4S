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
MAX_REVIEW_HINTS = 64
_SPACED_GLYPHS = re.compile(r'(?:\b[A-Za-z]\s+){6,}')
_ALT_WORD = re.compile(r'(?<![A-Za-z])[A-Za-z]{3,}(?![A-Za-z])')
_SHORT_PREFIX = re.compile(r'\b([A-Za-z]{1,2})\s+[A-Za-z]{5,}\b')
_SHORT_WORDS = frozenset({'a', 'i', 'an', 'as', 'at', 'be', 'by', 'do', 'go',
                          'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of',
                          'on', 'or', 's', 'so', 'to', 'up', 'us', 'we'})
# Captions and page furniture (running heads, page counters, licence and
# submission notes) that a text layer can splice into the middle of a body
# paragraph, typically at column or page breaks in two-column layouts.
_CAPTION_START = re.compile(
    r'^(?:FIGURE|Figure|FIG|Fig\.?|TABLE|Table|Scheme|SCHEME)\s*\d+[A-Za-z]?\s*(?:[|.:]|\s+[A-Z(])')
_PAGE_FURNITURE = re.compile(
    r'^\d{1,3}\s?of\s?\d{1,3}\b|\b\d{1,3}\s?of\s?\d{1,3}$|^(?:Received|Accepted|Published|Revised)\b'
    r'|Creative Commons|\b10\.\d{4,9}/\S+\s+\d{1,3}$|Check for updates|https?://doi\.org/|^©|\(\d{4}\)\s*\d+:\d+'
    r'|^(?:Article\s*)?https?://|^www\.')
_FURNITURE_MAX_LINE = 160
_SHORT_UNITS = frozenset({'cm', 'kg', 'km', 'mg', 'ml', 'mm', 'ms', 'ng',
                          'nm', 'ns', 'pm', 'ug', 'um'})


def _crosscheck_spacing(primary: str, alternate: str) -> list[dict[str, str]]:
    """Locate only character-identical word-join disagreements for human review.

    This is not a truth vote: two PDF parsers can both be wrong. The original
    pypdf text is not rewritten, and no hyphen, letter, digit or case changes
    are suggested here.
    """
    primary = unicodedata.normalize('NFKC', primary)
    alternate = unicodedata.normalize('NFKC', alternate)
    glyphs = [(match.group(), match.start(), match.end())
              for match in re.finditer(r'[^\s]', primary)]
    compact = ''.join(glyph for glyph, _, _ in glyphs)
    alternate_glyphs = [(match.group(), match.start())
                        for match in re.finditer(r'[^\s]', alternate)]
    alternate_compact = ''.join(glyph for glyph, _ in alternate_glyphs)
    alternate_offsets = {offset: index for index, (_, offset) in enumerate(alternate_glyphs)}
    suggestions = []
    seen = set()
    for word_match in _ALT_WORD.finditer(alternate):
        word = word_match.group()
        if len(word) > 64:
            continue
        if word != word.lower() or word == 'etal':
            continue
        line_start = alternate.rfind('\n', 0, word_match.start()) + 1
        line_end = alternate.find('\n', word_match.end())
        line = alternate[line_start:line_end if line_end >= 0 else len(alternate)]
        # A long line with almost no spaces is usually a collapsed column,
        # caption or reference. Its word boundaries are not a reliable vote.
        if len(line) >= 50 and line.count(' ') / len(line) < 0.09:
            continue
        alternate_position = alternate_offsets[word_match.start()]
        start = 0
        while (position := compact.find(word, start)) >= 0:
            start = position + 1
            observed = primary[glyphs[position][1]:glyphs[position + len(word) - 1][2]]
            parts = observed.split()
            if (len(parts) < 2 or ''.join(parts) != word or '\n' in observed
                    or not _matching_context(compact, position, alternate_compact,
                                             alternate_position, len(word))):
                continue
            # pdfplumber also merges many *real* adjacent words. Require a
            # distinctive short-prefix fracture or an all-glyph fracture.
            # A split after a full word ("chip s") is not enough evidence.
            if len(parts) == 2:
                if (len(parts[0]) > 2 or len(parts[1]) < 5
                        or parts[0].lower() in _SHORT_WORDS | _SHORT_UNITS):
                    continue
            elif not (len(word) >= 3 and all(len(part) <= 2 for part in parts)
                      and sum(len(part) == 1 for part in parts) * 2 >= len(parts)):
                continue
            key = (observed, word)
            if key not in seen:
                seen.add(key)
                suggestions.append({'observed': observed, 'suggestion': word})
                if len(suggestions) >= MAX_REVIEW_HINTS:
                    return suggestions
    return suggestions


def _matching_context(primary: str, primary_start: int, alternate: str,
                      alternate_start: int, length: int) -> bool:
    """Reject a same-spelled word borrowed from a different page location."""
    left_limit = min(12, primary_start, alternate_start)
    right_limit = min(12, len(primary) - primary_start - length,
                      len(alternate) - alternate_start - length)
    left = 0
    while (left < left_limit and primary[primary_start - left - 1]
           == alternate[alternate_start - left - 1]):
        left += 1
    right = 0
    while (right < right_limit and primary[primary_start + length + right]
           == alternate[alternate_start + length + right]):
        right += 1
    # Parser order can diverge after a title or column boundary. One strong
    # side, or two shorter matching sides, is enough to locate the same word.
    return max(left, right) >= 8 or (left >= 4 and right >= 4)


def _needs_spacing_crosscheck(text: str) -> bool:
    if _spacing_artifacts(text):
        return True
    return any(match.group(1).lower() not in _SHORT_WORDS | _SHORT_UNITS
               for match in _SHORT_PREFIX.finditer(text))


def _spacing_artifacts(text: str) -> bool:
    # PDFs with individually positioned glyphs can look readable while whole
    # scientific words are fractured into one-character tokens.
    return bool(_SPACED_GLYPHS.search(text))


def _review_excerpt(text: str, start: int, end: int) -> str:
    return re.sub(r'\s+', ' ', text[max(0, start - 35):min(len(text), end + 35)]).strip()[:140]


def _line_break_excerpt(left: str, right: str) -> str:
    """Show a line-end hyphen with whole surrounding words, not a fake fix."""
    left, right = left.strip(), right.strip()
    before = left[-60:]
    if len(left) > 60 and not left[-61].isspace() and ' ' in before:
        before = before.split(' ', 1)[1]
    after = right[:60]
    if len(right) > 60 and not right[60].isspace() and ' ' in after:
        after = after.rsplit(' ', 1)[0]
    return before + ' / ' + after


def _furniture_hints(lines: list[str], page: int) -> list[dict[str, str]]:
    """Locate lines that look like captions or page furniture; never remove them."""
    hints = []
    for line in lines:
        if _CAPTION_START.match(line) or (len(line) <= _FURNITURE_MAX_LINE and _PAGE_FURNITURE.search(line)):
            hints.append({'page': page, 'kind': 'PROBABLE_CAPTION_OR_PAGE_FURNITURE',
                          'excerpt': line[:120]})
    return hints


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
    alternate_pdf = None
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported')
        count = len(reader.pages)
        if not 0 < count <= MAX_PAGES:
            raise ValueError('PDF must contain 1 to 32 pages')
        paragraphs = []
        warnings = {'READING_ORDER_REQUIRES_REVIEW', 'PARAGRAPH_BOUNDARIES_REQUIRE_REVIEW'}
        review_hints_by_page = []
        image_count = 0
        # An independent character-position parser is used only to locate
        # possible word-spacing defects; its full text never replaces pypdf.
        for number, page in enumerate(reader.pages, start=1):
            page_hints = []
            review_hints_by_page.append(page_hints)
            images = len(page.images)
            image_count += images
            if images:
                warnings.add('IMAGE_TEXT_NOT_EXTRACTED')
            raw = page.extract_text(extraction_mode='plain') or ''
            if _needs_spacing_crosscheck(raw):
                try:
                    if alternate_pdf is None:
                        import pdfplumber
                        alternate_pdf = pdfplumber.open(io.BytesIO(data))
                    alternate_text = alternate_pdf.pages[number - 1].extract_text() or ''
                    for suggestion in _crosscheck_spacing(raw, alternate_text):
                        if len(page_hints) < MAX_REVIEW_HINTS:
                            page_hints.append({'page': number,
                                               'kind': 'CROSS_EXTRACTOR_SPACING_SUGGESTION',
                                               'excerpt': suggestion['observed'],
                                               'suggestion': suggestion['suggestion']})
                        else:
                            warnings.add('REVIEW_HINTS_TRUNCATED')
                    if any(hint['kind'] == 'CROSS_EXTRACTOR_SPACING_SUGGESTION' for hint in page_hints):
                        warnings.add('CROSS_EXTRACTOR_SPACING_REQUIRES_REVIEW')
                except Exception:
                    # A second parser must never turn a readable pypdf import
                    # into a failed upload or silently change the primary text.
                    warnings.add('SECOND_EXTRACTOR_UNAVAILABLE')
            spaced = _SPACED_GLYPHS.search(raw)
            if spaced:
                warnings.add('TEXT_SPACING_ARTIFACTS')
                if len(page_hints) < MAX_REVIEW_HINTS:
                    page_hints.append({'page': number, 'kind': 'TEXT_SPACING_ARTIFACTS',
                                       'excerpt': _review_excerpt(raw, spaced.start(), spaced.end())})
                else:
                    warnings.add('REVIEW_HINTS_TRUNCATED')
            furniture = _furniture_hints([line.strip() for line in raw.splitlines() if line.strip()], number)
            if furniture:
                warnings.add('CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW')
                # Structural interruptions are listed before glyph-level hints.
                for hint in reversed(furniture):
                    page_hints.insert(0, hint)
            groups, split = _chunks(raw)
            if not groups:
                warnings.add('NO_TEXT_LAYER')
            if split:
                warnings.add('PAGE_CHUNK_BOUNDARY_REQUIRES_REVIEW')
            for group in groups:
                text, line_end_hyphen = _normalise_lines(group)
                if line_end_hyphen:
                    warnings.add('LINE_END_HYPHEN_REQUIRES_REVIEW')
                    lines = [line.strip() for line in group.splitlines() if line.strip()]
                    for index, line in enumerate(lines[:-1]):
                        if line.endswith('-'):
                            if len(page_hints) < MAX_REVIEW_HINTS:
                                page_hints.append({'page': number, 'kind': 'LINE_END_HYPHEN_REQUIRES_REVIEW',
                                                   'excerpt': _line_break_excerpt(line, lines[index + 1])})
                            else:
                                warnings.add('REVIEW_HINTS_TRUNCATED')
                paragraphs.append({'page': number, 'bbox': None,
                                   'column': 'unverified', 'text': text})
        # Share the bounded hint budget across pages before restoring page order.
        # Otherwise a hyphen-heavy first page can conceal later-page warnings.
        review_hints = []
        for offset in range(MAX_REVIEW_HINTS):
            added = False
            for page_hints in review_hints_by_page:
                if offset < len(page_hints):
                    review_hints.append(page_hints[offset])
                    added = True
                    if len(review_hints) == MAX_REVIEW_HINTS:
                        break
            if len(review_hints) == MAX_REVIEW_HINTS or not added:
                break
        if sum(len(page_hints) for page_hints in review_hints_by_page) > MAX_REVIEW_HINTS:
            warnings.add('REVIEW_HINTS_TRUNCATED')
        review_hints.sort(key=lambda hint: hint['page'])
        if len(paragraphs) > 128:
            raise ValueError('PDF produced more than 128 text chunks; select fewer pages')
        text = '\n\n'.join(item['text'] for item in paragraphs)
        if len(text) > MAX_TEXT_CHARS:
            raise ValueError('Extracted text is too long; select a shorter PDF')
        return {'pages': count, 'image_count': image_count,
                'paragraphs': paragraphs, 'warnings': sorted(warnings), 'review_hints': review_hints,
                'review_required': True,
                'segmentation': 'page_text_chunks_unverified',
                'source_pdf_sha256': hashlib.sha256(data).hexdigest(),
                'extracted_text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
    except (PdfReadError, KeyError, TypeError, RecursionError) as error:
        raise ValueError('Could not read PDF') from error
    finally:
        if alternate_pdf is not None:
            alternate_pdf.close()
