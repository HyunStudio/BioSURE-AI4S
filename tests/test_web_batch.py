from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from biosure.web_demo import make_server


@pytest.fixture
def service():
    server = make_server(ROOT / "fixtures", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def post(service, body, **headers):
    request = urllib.request.Request(service + "/api/batch", data=body,
                                     headers={"Content-Type": "application/json", **headers})
    return urllib.request.urlopen(request, timeout=4)


def test_fixed_fictional_sample_can_be_run_as_batch_without_gold(service):
    # A missing route, wrong fixture, or count/ordering bug must fail this.
    with urllib.request.urlopen(service + "/api/examples/batch", timeout=4) as response:
        records = json.load(response)
    assert len(records) == 6
    assert all(set(item) == {"record_id", "reference_paragraphs", "observed_paragraphs"} for item in records)
    with post(service, json.dumps(records).encode()) as response:
        assert response.headers["Cache-Control"] == "no-store"
        result = json.load(response)
    assert result["summary"] == {"records": 6, "automatic": 2, "unchanged": 1, "review_required": 3}
    assert [item["request"]["damaged"]["record_id"] for item in result["results"]] == [item["record_id"] for item in records]
    assert result["results"][0]["selected_paragraphs"] == records[0]["reference_paragraphs"]
    assert "gold" not in result


@pytest.mark.parametrize("body", [b'[]', b'{}', b'[null]',
    b'[{"record_id":"one","reference_paragraphs":["A","B","C"],"reference_paragraphs":["A","X","C"],"observed_paragraphs":["A","C"]}]',
    b'[{"record_id":"ok","reference_paragraphs":["A","B","C"],"observed_paragraphs":["A","C"]},null]'])
def test_batch_invalid_input_is_all_or_nothing(service, body):
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(service, body)
    assert caught.value.code == 400
    result = json.loads(caught.value.read())
    assert set(result) == {"error"}  # No successful-prefix results/prose.


def test_duplicate_batch_record_ids_rejected(service):
    record = {"record_id": "same", "reference_paragraphs": ["A", "B", "C"], "observed_paragraphs": ["A", "C"]}
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(service, json.dumps([record, record]).encode())
    assert caught.value.code == 400


def test_batch_cross_origin_request_rejected_before_processing(service):
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(service, b'[]', Origin="https://example.org")
    assert caught.value.code == 403


def test_batch_http_size_limit_is_not_weakened(service):
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(service, b" " * 1048577)
    assert caught.value.code == 413


def test_batch_wrong_content_type_rejected(service):
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(service, b'[]', **{"Content-Type": "text/plain"})
    assert caught.value.code == 415


def test_batch_script_is_served_as_javascript(service):
    with urllib.request.urlopen(service + "/batch.js", timeout=4) as response:
        assert response.headers.get_content_type() == "text/javascript"
        assert len(response.read()) > 0
