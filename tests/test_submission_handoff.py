from biosure.workflow import run_workflow
import pytest
from biosure import workflow
import json
import threading
import urllib.request
from pathlib import Path
from biosure.web_demo import make_server
from biosure.cli import main


def test_review_preserves_normalized_inputs_without_applying_unsupported_text():
    result = run_workflow({'record_id': 'review', 'reference_paragraphs': [' A ', 'B', 'C'],
                           'observed_paragraphs': ['A', 'altered', 'C']})
    assert result['reference_paragraphs'] == ['A', 'B', 'C']
    assert result['observed_paragraphs'] == ['A', 'altered', 'C']
    assert result['selected_paragraphs'] is None

@pytest.mark.parametrize('proposed,status', [(['A','B','C'],'PROPOSAL_REVIEW_REQUIRED'),
    (['A','invented','C'],'PROPOSAL_REJECTED'), (['A','B','changed'],'PROPOSAL_REJECTED'),
    (['A','C','B'],'PROPOSAL_REJECTED'), (['A','B','B','C'],'PROPOSAL_REJECTED')])
def test_external_proposal_is_checked_not_silently_replaced(proposed, status):
    result = workflow.run_proposal({'record_id': 'external', 'reference_paragraphs': ['A','B','C'],
        'observed_paragraphs': ['A','C'], 'proposed_paragraphs': proposed})
    assert result['decision']['action'] == 'ABSTAIN'
    assert result['selected_paragraphs'] is None
    assert result['adapter_status'] == status
    assert result['proposed_paragraphs'] == proposed
    assert result['proposal_sha256']

def test_proposal_cannot_authorize_an_unsupported_original_difference():
    result = workflow.run_proposal({'record_id': 'unsupported', 'reference_paragraphs': ['A','B','C'],
        'observed_paragraphs': ['A','altered','C'], 'proposed_paragraphs': ['A','B','C']})
    assert result['decision']['action'] == 'ABSTAIN'
    assert result['selected_paragraphs'] is None

def test_proposal_rejects_outcome_labels():
    with pytest.raises(ValueError):
        workflow.run_proposal({'record_id': 'leak', 'reference_paragraphs': ['A','B','C'],
            'observed_paragraphs': ['A','C'], 'proposed_paragraphs': ['A','B','C'], 'gold': True})

def test_proposal_endpoint_uses_actual_upstream_text():
    server = make_server(Path(__file__).resolve().parents[1] / 'fixtures', port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        body = {'record_id': 'api', 'reference_paragraphs': ['A','B','C'],
            'observed_paragraphs': ['A','C'], 'proposed_paragraphs': ['A','invented','C']}
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_address[1]}/api/proposal',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=4) as response:
            result = json.load(response)
        assert result['decision']['action'] == 'ABSTAIN'
        assert result['selected_paragraphs'] is None
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=2)

def test_proposal_cli_is_offline_and_does_not_change_input(tmp_path, capsys):
    body = {'record_id': 'cli', 'reference_paragraphs': ['A','B','C'],
        'observed_paragraphs': ['A','C'], 'proposed_paragraphs': ['A','B','C']}
    path = tmp_path / 'proposal.json'; path.write_text(json.dumps(body), encoding='utf-8')
    before = path.read_bytes()
    assert main(['proposal', '--input', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['selected_paragraphs'] is None
    assert path.read_bytes() == before

def test_rejected_proposal_receipt_binds_actual_proposal_even_without_supported_edit():
    body = {'record_id': 'receipt', 'reference_paragraphs': ['A','B','C'],
        'observed_paragraphs': ['A','altered','C'], 'proposed_paragraphs': ['A','B','C']}
    first = workflow.run_proposal(body)
    second = workflow.run_proposal({**body, 'proposed_paragraphs': ['A','invented','C']})
    assert first['proposal_receipt']['receipt_sha256'] != second['proposal_receipt']['receipt_sha256']
    assert first['proposal_receipt'] == workflow.run_proposal(body)['proposal_receipt']

def test_external_duplicate_removal_is_review_only_even_with_actual_text():
    result = workflow.run_proposal({'record_id': 'dedup', 'reference_paragraphs': ['A','B','C'],
        'observed_paragraphs': ['A','B','B','C'], 'proposed_paragraphs': ['A','B','C']})
    assert result['selected_paragraphs'] is None
    assert result['adapter_status'] == 'PROPOSAL_REVIEW_REQUIRED'
