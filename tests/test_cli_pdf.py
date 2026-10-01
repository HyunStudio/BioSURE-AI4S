import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

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


def test_cli_pdf_extract_emits_valid_json_in_cp949_windows_console(tmp_path):
    stream = BytesIO(); document = canvas.Canvas(stream)
    document.drawString(50, 770, 'OoC–WAT text layer')
    document.showPage(); document.save()
    source = tmp_path / 'unicode-paper.pdf'; source.write_bytes(stream.getvalue())
    env = {**os.environ, 'PYTHONIOENCODING': 'cp949', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-m', 'biosure.cli', 'pdf-extract', '--input', str(source)],
                            cwd=Path(__file__).resolve().parents[1], env=env,
                            capture_output=True, text=True, encoding='cp949', check=False)
    assert result.returncode == 0, result.stderr
    assert 'OoC–WAT text layer' in json.loads(result.stdout)['paragraphs'][0]['text']
