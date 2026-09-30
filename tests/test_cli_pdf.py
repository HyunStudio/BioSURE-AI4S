import json
from io import BytesIO

from reportlab.pdfgen import canvas

from biosure.cli import main


def test_cli_pdf_extract_prints_reviewable_json(tmp_path, capsys):
    stream = BytesIO(); document = canvas.Canvas(stream)
    document.drawString(50, 770, 'Research evidence paragraph.')
    document.showPage(); document.save()
    source = tmp_path / 'paper.pdf'; source.write_bytes(stream.getvalue())
    assert main(['pdf-extract', '--input', str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['review_required'] is True
    assert result['paragraphs'][0]['text'] == 'Research evidence paragraph.'


def test_cli_pdf_extract_rejects_non_pdf(tmp_path, capsys):
    source = tmp_path / 'bad.pdf'; source.write_bytes(b'bad')
    assert main(['pdf-extract', '--input', str(source)]) == 2
    assert 'BioSURE input error' in capsys.readouterr().err
