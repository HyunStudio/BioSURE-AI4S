import json
import threading
import urllib.request
from pathlib import Path

import pytest

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


def test_learned_review_never_changes_gate_action_and_returns_bound_rankings(service):
    payload = {'record_id':'learned-review-demo',
               'reference_paragraphs':['Reference methods paragraph with 5 mg in microfluidic channels.',
                                       'Results did not increase in the control group.',
                                       'Closing note records no clinical claims.'],
               'observed_paragraphs':['Reference methods paragraph with 6 mg in microfluidic channels.',
                                      'Results did not increase in the control group.',
                                      'Closing note records no clinical claims.']}
    request = urllib.request.Request(service + '/api/ml-review',
                                     data=json.dumps(payload).encode(),
                                     headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.load(response)
    assert result['mode'] == 'learned_correspondence_review'
    assert result['decision']['action'] == 'ABSTAIN'
    assert result['correspondences'][0]['reference_index'] == 0
    assert 'NUMBER_CHANGED' in result['correspondences'][0]['flags']
    assert result['ml_receipt']['gate_receipt_sha256'] == result['receipt']['receipt_sha256']


def test_public_ml_summary_discloses_tie_without_source_prose(service):
    with urllib.request.urlopen(service + '/api/ml-summary', timeout=5) as response:
        result = json.load(response)
    assert result['sources'] == {'train': 12, 'dev': 6, 'test': 6}
    assert result['queries'] == 284
    assert result['learned_correct'] == result['best_lexical_correct'] == 284
    assert result['accuracy_delta'] == 0.0
    assert result['unit_control_positives'] == 8
    assert 'paragraphs' not in result
