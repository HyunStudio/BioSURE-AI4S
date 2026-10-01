"""PDF import must expose losses; generated test PDFs contain no private work."""
from io import BytesIO

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from biosure.pdf_extract import _normalise_lines, extract_pdf


def made_pdf(with_image=False, with_text=True):
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(595,842))
    if with_text:
        doc.drawString(50,772,'Scientific document example')
        doc.drawString(50,542,'We examined quantifi-')
        doc.drawString(50,526,'cation in microfluidic channels.')
        doc.drawString(330,542,'Results from the other column.')
    if with_image:
        image = Image.new('RGB',(3,3),'white')
        doc.drawImage(ImageReader(image),50,380,width=150,height=100)
    doc.showPage(); doc.save()
    return stream.getvalue()


def test_pdf_import_preserves_text_and_page_provenance_without_claiming_layout():
    result = extract_pdf(made_pdf())
    assert result['pages'] == 1
    assert result['segmentation'] == 'page_text_chunks_unverified'
    assert result['paragraphs'][0]['page'] == 1
    assert result['paragraphs'][0]['bbox'] is None
    assert result['paragraphs'][0]['column'] == 'unverified'
    text = ' '.join(item['text'] for item in result['paragraphs'])
    assert 'Scientific document example' in text
    assert 'We examined quantifi-cation in microfluidic channels.' in text
    assert 'Results from the other column.' in text
    assert 'LINE_END_HYPHEN_REQUIRES_REVIEW' in result['warnings']
    assert 'READING_ORDER_REQUIRES_REVIEW' in result['warnings']
    assert 'PARAGRAPH_BOUNDARIES_REQUIRE_REVIEW' in result['warnings']
    assert result['review_required'] is True
    assert len(result['source_pdf_sha256']) == 64


def test_embedded_image_text_is_not_misrepresented_as_extracted():
    result = extract_pdf(made_pdf(with_image=True))
    assert 'IMAGE_TEXT_NOT_EXTRACTED' in result['warnings']
    assert result['image_count'] == 1


def test_scientific_pdf_ligatures_normalise_to_searchable_words():
    text, _ = _normalise_lines('Existing workﬂows need quantiﬁcation.')
    assert text == 'Existing workflows need quantification.'


def test_pdf_line_end_hyphen_preserves_original_glyph_for_manual_review():
    text, review = _normalise_lines('organ-on-a-\nchip and quantifi-\ncation')
    assert text == 'organ-on-a-chip and quantifi-cation'
    assert review is True


def test_spacing_artifacts_are_flagged_instead_of_claiming_clean_extraction():
    from biosure.pdf_extract import _spacing_artifacts
    assert _spacing_artifacts('B r y s o n D . P . G r a y') is True
    assert _spacing_artifacts('Normal scientific prose with proper spaces.') is False


def test_image_only_page_requires_review_with_no_invented_text():
    result = extract_pdf(made_pdf(with_image=True, with_text=False))
    assert result['paragraphs'] == []
    assert 'NO_TEXT_LAYER' in result['warnings']


@pytest.mark.parametrize('blob', [b'',b'not pdf',b'%PDF-1.4'+b'X'*16_777_216], ids=['empty','not-pdf','oversized'])
def test_invalid_or_oversize_file_fails(blob):
    with pytest.raises(ValueError): extract_pdf(blob)
