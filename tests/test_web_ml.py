import json
import threading
import urllib.error
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


def test_public_ml_summary_separates_real_source_holdout_from_constructed_benchmark(service):
    with urllib.request.urlopen(service + '/api/ml-summary', timeout=5) as response:
        result = json.load(response)
    real = result['real_source_audit']
    assert real['development_sources'] == real['held_out_sources'] == 4
    assert real['held_out_units'] == 8
    assert real['learned_rank_correct'] == 7
    assert real['difflib_rank_correct'] == real['token_dice_rank_correct'] == 8
    assert real['direct_copy_exact'] == 8
    assert real['reversed_reference_exact'] == 0
    assert 'gold is the same article' in real['scope'].lower()
    assert len(real['sources']) == 8
    assert [(row['source_id'], row['learned_rank_correct'], row['proposal_status'])
            for row in real['sources'] if row['learned_rank_correct'] != 2] == [
                ('PMC12864593', 1, 'ABSTAIN'), ('PMC12789962', 1, 'ABSTAIN')]


def test_learned_upstream_endpoint_returns_a_bound_review_candidate_without_edit_authority(service):
    payload = {'record_id': 'learned-upstream-http',
               'reference_paragraphs': ['Reference methods paragraph with 5 mg in microfluidic channels.',
                                        'Results did not increase in the control group.'],
               'observed_paragraphs': ['Reference methods paragraph with 5 mg in microfluidic channels!',
                                      'Results did not increase in the control group.']}
    request = urllib.request.Request(service + '/api/learned-proposal',
                                     data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.load(response)
    assert result['mode'] == 'learned_upstream_proposal'
    assert result['proposal_status'] == 'PROPOSED_FOR_REVIEW'
    assert result['proposed_paragraphs'] == payload['reference_paragraphs']
    assert result['proposal_check']['decision']['action'] == 'ABSTAIN'
    assert result['proposal_check']['selected_paragraphs'] is None
    assert result['upstream_receipt']['receipt_sha256']
    assert 'decision' not in result


def test_learned_http_abstention_does_not_publish_baseline_selection(service):
    payload = {'record_id': 'review',
               'reference_paragraphs': ['The channel was washed.', 'THE CHANNEL WAS WASHED.', 'Closing paragraph.'],
               'observed_paragraphs': ['The channel was washed.', 'Closing paragraph.']}
    request = urllib.request.Request(service + '/api/learned-proposal', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        result = json.load(response)
    assert result['proposal_status'] == 'ABSTAIN'
    assert result['proposal_check'] is None
    assert result['original_workflow_review']['decision']['action'] == 'ABSTAIN'
    assert 'selected_paragraphs' not in result
    assert 'decision' not in result


def test_public_extraction_example_loads_attributed_observed_input_without_gold(service):
    with urllib.request.urlopen(service + '/api/examples/public-extraction?source=PMC12864593', timeout=5) as response:
        result = json.load(response)
    assert result['source_id'] == 'PMC12864593'
    assert result['split'] == 'development'
    assert result['source']['pmcid'] == 'PMC12864593'
    assert result['source']['license_uri'] == 'https://creativecommons.org/licenses/by/4.0/'
    assert len(result['reference_paragraphs']) == len(result['observed_paragraphs']) == 2
    assert result['reference_paragraphs'] != result['observed_paragraphs']
    assert 'gold' not in result
    assert 'pdf_sha256' in result['source']
    with pytest.raises(urllib.error.HTTPError) as rejected:
        urllib.request.urlopen(service + '/api/examples/public-extraction?source=PMC99999999', timeout=5)
    assert rejected.value.code == 400
