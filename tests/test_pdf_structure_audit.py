"""Structure audit mechanics on a generated PDF and authored JATS; no article text."""
from io import BytesIO

from reportlab.pdfgen import canvas

from scripts.audit_pdf_structure import audit_pair, jats_paragraphs

BODY_A = ("The perfused barrier model was cultured for three days under constant flow and the "
          "endothelial layer remained confluent across every channel that was examined in this work, "
          "with daily imaging confirming that no detachment occurred at the inlet or outlet regions.")
BODY_B = ("A second independent paragraph describes the permeability measurements that were "
          "performed after the culture period ended and compares them with static control wells, "
          "reporting tracer flux for each device separately rather than as one pooled average value.")


def pdf_with_spliced_caption():
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(595, 842))
    y = 800
    words = BODY_A.split()
    lines = [' '.join(words[:12]), 'FIGURE 1 Schematic of the perfusion circuit.', ' '.join(words[12:])]
    lines += [BODY_B[i:i + 80] for i in range(0, len(BODY_B), 80)]
    for line in lines:
        doc.drawString(40, y, line)
        y -= 16
    doc.showPage(); doc.save()
    return stream.getvalue()


JATS = f"<article><body><sec><p id='a'>{BODY_A}</p><fig><caption><p>caption</p></caption></fig><p>{BODY_B}</p></sec></body></article>"


def test_jats_paragraphs_skip_figures_and_attributes():
    assert jats_paragraphs(JATS) == [BODY_A, BODY_B]


def test_spliced_caption_is_counted_and_located_by_hint():
    row = audit_pair(pdf_with_spliced_caption(), JATS)
    assert (row["paragraphs"], row["intact"], row["split"], row["lost"]) == (2, 1, 1, 0)
    assert (row["inserts"], row["caption_inserts"], row["inserts_located_by_hint"]) == (1, 1, 1)
    assert row["order_inversions"] == 0


def pdf_with_deleted_middle():
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(595, 842))
    y = 800
    damaged = BODY_A.replace("remained confluent across every channel", "")
    for i in range(0, len(damaged), 80):
        doc.drawString(40, y, damaged[i:i + 80]); y -= 16
    for i in range(0, len(BODY_B), 80):
        doc.drawString(40, y, BODY_B[i:i + 80]); y -= 16
    doc.showPage(); doc.save()
    return stream.getvalue()


def test_deleted_middle_text_is_unverified_not_counted_as_a_splice():
    row = audit_pair(pdf_with_deleted_middle(), JATS)
    assert (row["intact"], row["split"], row["unverified"], row["lost"]) == (1, 0, 1, 0)
    assert row["inserts"] == 0
