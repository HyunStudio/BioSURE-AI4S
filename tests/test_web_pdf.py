"""The local PDF boundary must be bounded, same-origin, and candid about omissions."""
import json
from io import BytesIO
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from biosure.web_demo import make_server


@pytest.fixture
def service():
    server = make_server(Path(__file__).resolve().parents[1] / 'fixtures', port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)


def pdf_data():
    stream = BytesIO(); document = canvas.Canvas(stream)
    document.drawString(50, 770, 'Source paragraph with quantification.')
    document.showPage(); document.save()
    return stream.getvalue()


def test_pdf_upload_returns_provenance_for_review_without_persisting_bytes(service):
    request = urllib.request.Request(service + '/api/pdf-extract', data=pdf_data(),
                                     headers={'Content-Type': 'application/pdf'})
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.load(response)
        assert response.headers['Cache-Control'] == 'no-store'
    assert result['review_required'] is True
    assert result['paragraphs'][0]['text'] == 'Source paragraph with quantification.'
    assert result['paragraphs'][0]['page'] == 1
    assert len(result['source_pdf_sha256']) == 64


def test_pdf_upload_rejects_cross_origin(service):
    request = urllib.request.Request(service + '/api/pdf-extract', data=pdf_data(),
                                     headers={'Content-Type': 'application/pdf', 'Origin': 'https://evil.example'})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 403


def test_pdf_upload_rejects_wrong_type_and_malformed_bytes(service):
    for body, content_type, expected in [(pdf_data(), 'text/plain', 415), (b'bad', 'application/pdf', 400)]:
        request = urllib.request.Request(service + '/api/pdf-extract', data=body,
                                         headers={'Content-Type': content_type})
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        assert caught.value.code == expected


def test_pdf_upload_limit_is_separate_from_one_mib_json_limit(service):
    request = urllib.request.Request(service + '/api/pdf-extract', data=b'%PDF-1.4' + b'X' * (16 * 1024 * 1024),
                                     headers={'Content-Type': 'application/pdf'})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 413
