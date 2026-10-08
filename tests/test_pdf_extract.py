"""PDF import must expose losses; generated test PDFs contain no private work."""
from io import BytesIO
import sys

import pytest
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from biosure.pdf_extract import _crosscheck_spacing, _needs_spacing_crosscheck, _normalise_lines, extract_pdf


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


def test_pdf_review_hints_locate_a_preserved_line_end_hyphen_without_claiming_a_fix():
    result = extract_pdf(made_pdf())
    assert any(hint['page'] == 1 and hint['kind'] == 'LINE_END_HYPHEN_REQUIRES_REVIEW'
               and 'quantifi-' in hint['excerpt'] for hint in result['review_hints'])
    assert result['review_required'] is True


def test_pdf_review_hints_locate_spaced_glyphs():
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    doc.drawString(72, 700, 'f o r d r u g d i s c o v e r y')
    doc.save()
    result = extract_pdf(stream.getvalue())
    assert any(hint['page'] == 1 and hint['kind'] == 'TEXT_SPACING_ARTIFACTS'
               and 'd i s c o v e r y' in hint['excerpt'] for hint in result['review_hints'])


def test_failed_second_parser_leaves_primary_pdf_text_available(monkeypatch):
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    doc.drawString(72, 700, 'f o r d r u g d i s c o v e r y')
    doc.save()
    monkeypatch.setitem(sys.modules, 'pdfplumber', None)
    result = extract_pdf(stream.getvalue())
    assert 'SECOND_EXTRACTOR_UNAVAILABLE' in result['warnings']
    assert 'f o r d r u g d i s c o v e r y' in result['paragraphs'][0]['text']
    assert result['review_required'] is True


def test_pdf_review_hint_cap_preserves_later_page_coverage():
    stream = BytesIO()
    doc = canvas.Canvas(stream)
    for index in range(70):
        doc.drawString(50, 800 - index * 9, f'First-page scientific term {index} pre-')
        doc.drawString(50, 796 - index * 9, f'fix{index} continues the sentence.')
    doc.showPage()
    doc.drawString(50, 700, 'Later-page scientific term quantifi-')
    doc.drawString(50, 680, 'cation matters here.')
    doc.save()

    result = extract_pdf(stream.getvalue())
    assert len(result['review_hints']) == 64
    assert 'REVIEW_HINTS_TRUNCATED' in result['warnings']
    assert any(hint['page'] == 2 and 'quantifi-' in hint['excerpt']
               for hint in result['review_hints'])


def test_hyphen_hint_excerpt_does_not_start_or_end_with_a_clipped_word():
    from biosure.pdf_extract import _line_break_excerpt
    left = 'An unusually long intro with cells that mirror human organs and faith-'
    right = 'fully simulate their microfluidic environment with a long tail'
    excerpt = _line_break_excerpt(left, right)
    before, after = excerpt.split(' / ')
    assert before.split()[0] in left.split()
    assert after.split()[-1] in right.split()
    assert 'faith- / fully' in excerpt


def test_spacing_artifacts_are_flagged_instead_of_claiming_clean_extraction():
    from biosure.pdf_extract import _spacing_artifacts
    assert _spacing_artifacts('B r y s o n D . P . G r a y') is True
    assert _spacing_artifacts('Normal scientific prose with proper spaces.') is False


def test_second_extractor_locates_broken_word_spacing_without_changing_primary_text():
    primary = 'The excretory system ensures elimination ef ficiency akin to in vivo conditions.'
    alternate = 'The excretory system ensures elimination efficiency akin to in vivo conditions.'
    assert _crosscheck_spacing(primary, alternate) == [
        {'observed': 'ef ficiency', 'suggestion': 'efficiency'}]


def test_second_extractor_does_not_borrow_matching_word_from_unrelated_context():
    primary = 'The ef ficiency improved cellular transport. An unrelated section follows.'
    alternate = 'The efficacy improved cellular transport. An unrelated efficiency result follows.'
    assert _crosscheck_spacing(primary, alternate) == []


def test_second_extractor_does_not_join_fragments_across_lines():
    assert _crosscheck_spacing('The h a\ns value was reported.',
                               'The has value was reported.') == []


def test_second_extractor_does_not_join_scientific_units_to_nouns():
    assert _crosscheck_spacing('The amount was mg tissue in the sample.',
                               'The amount was mgtissue in the sample.') == []
    assert _crosscheck_spacing('A mm thick layer was prepared.',
                               'A mmthick layer was prepared.') == []


def test_second_extractor_ignores_low_quality_glued_text_line():
    primary = 'observedlongcontextbefore d r u ge n g a g e rt o followedlongcontextafter'
    alternate = 'observedlongcontextbefore drugengagerto followedlongcontextafter'
    assert _crosscheck_spacing(primary, alternate) == []


def test_second_extractor_does_not_suggest_semantic_or_hyphen_changes():
    assert _crosscheck_spacing('The result was faith-fully reproduced.',
                               'The result was faithfully reproduced.') == []
    assert _crosscheck_spacing('The dose was 10 mg.', 'The dose was 100 mg.') == []
    assert _crosscheck_spacing('Cells were cultured in vitro.',
                               'Cells were cultured invitro.') == []
    assert _crosscheck_spacing('The design and fabrication of the system',
                               'Thedesignandfabricationofthesystem') == []
    assert _crosscheck_spacing('Organ-on-chip s', 'Organ-on-chips') == []
    assert _crosscheck_spacing('Li et al described it.', 'Lietal described it.') == []
    assert _crosscheck_spacing('e ta l cited it.', 'etal cited it.') == []
    assert _crosscheck_spacing('the method s three stages', 'the method sthree stages') == []
    assert _crosscheck_spacing('xt is a marker', 'xtisa marker') == []
    assert _crosscheck_spacing('D convolutions were used', 'Dconvolutions were used') == []


def test_second_extractor_catches_multiple_fractured_title_words():
    primary = 'An eighteen-organ system f o rd r u gd i s c o v e r y'
    alternate = 'An eighteen-organ system for drug discovery'
    assert _crosscheck_spacing(primary, alternate) == [
        {'observed': 'f o r', 'suggestion': 'for'},
        {'observed': 'd r u g', 'suggestion': 'drug'},
        {'observed': 'd i s c o v e r y', 'suggestion': 'discovery'}]


def test_second_extractor_keeps_title_words_when_following_line_differs():
    primary = 'An eighteen-organ system f o rd r u gd i s c o v e r y\nJing Wang'
    alternate = 'An eighteen-organ system for drug discovery\n✉\nJing Wang'
    assert _crosscheck_spacing(primary, alternate) == [
        {'observed': 'f o r', 'suggestion': 'for'},
        {'observed': 'd r u g', 'suggestion': 'drug'},
        {'observed': 'd i s c o v e r y', 'suggestion': 'discovery'}]


def test_second_extractor_does_not_emit_unbounded_word_candidates():
    assert _crosscheck_spacing(' '.join('x' * 80), 'x' * 80) == []


def test_second_extractor_runs_for_short_prefix_fractures_not_ordinary_small_words():
    assert _needs_spacing_crosscheck('Elimination ef ficiency increased.') is True
    assert _needs_spacing_crosscheck('Cells grown in vitro in a study.') is False
    assert _needs_spacing_crosscheck('A mm thick layer was prepared.') is False
    assert _needs_spacing_crosscheck('The mg tissue ratio was recorded.') is False


def test_image_only_page_requires_review_with_no_invented_text():
    result = extract_pdf(made_pdf(with_image=True, with_text=False))
    assert result['paragraphs'] == []
    assert 'NO_TEXT_LAYER' in result['warnings']


@pytest.mark.parametrize('blob', [b'',b'not pdf',b'%PDF-1.4'+b'X'*16_777_216], ids=['empty','not-pdf','oversized'])
def test_invalid_or_oversize_file_fails(blob):
    with pytest.raises(ValueError): extract_pdf(blob)


def furniture_pdf():
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(595, 842))
    doc.drawString(50, 800, 'Advanced Science, 2026 3 of 31')
    doc.drawString(50, 772, 'The chip was perfused for three days and the')
    doc.drawString(50, 756, 'FIGURE 2 Schematic of the perfusion circuit.')
    doc.drawString(50, 740, 'barrier remained intact throughout culture.')
    doc.drawString(50, 724, 'Figure 2 shows that the barrier remained intact.')
    doc.showPage(); doc.save()
    return stream.getvalue()


def test_caption_and_page_furniture_are_located_but_never_removed():
    result = extract_pdf(furniture_pdf())
    text = ' '.join(item['text'] for item in result['paragraphs'])
    assert 'FIGURE 2 Schematic of the perfusion circuit.' in text
    assert 'Advanced Science, 2026 3 of 31' in text
    assert 'CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW' in result['warnings']
    flagged = [hint['excerpt'] for hint in result['review_hints']
               if hint['kind'] == 'PROBABLE_CAPTION_OR_PAGE_FURNITURE']
    assert 'FIGURE 2 Schematic of the perfusion circuit.' in flagged
    assert 'Advanced Science, 2026 3 of 31' in flagged
    # An in-text figure reference and ordinary body lines are not flagged.
    assert not any(item.startswith(('Figure 2 shows', 'The chip', 'barrier')) for item in flagged)


@pytest.mark.parametrize('line', [
    'Fig. 1 | Mini-bladder model of the human urothelium',
    'FIG 3 Cytokine production in the maternal chamber',
    'Figure 4. Barrier integrity after reperfusion',
    'TABLE 1 Versatility of composites',
    'Nature Communications | (2026) 17:2322 5',
    'Infection and Immunity December 2025 Volume 93 Issue 12 10.1128/iai.00346-25 2',
    'Received: 14 February 2025',
])
def test_caption_and_furniture_patterns(line):
    from biosure.pdf_extract import _furniture_hints
    assert _furniture_hints([line], 1)


@pytest.mark.parametrize('line', [
    'Figure 2 shows that cells remained viable',
    'cells were seeded in 3 of 4 wells and the medium',
    'as described previously (doi:10.1038/s41467-026-68573-3).',
])
def test_body_text_is_not_flagged_as_furniture(line):
    from biosure.pdf_extract import _furniture_hints
    assert not _furniture_hints([line], 1)
