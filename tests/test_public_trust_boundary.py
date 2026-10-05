"""Caller text or graph evidence must not authorize public automatic repair."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from biosure.batch import run_batch
from biosure.schema import loads_json
from biosure.web_demo import make_server
from biosure.workflow import run_proposal, run_workflow


ROOT = Path(__file__).resolve().parents[1]
OMISSION = {"record_id": "arbitrary", "reference_paragraphs": ["A", "B", "C"],
            "observed_paragraphs": ["A", "C"]}
DUPLICATE = {**OMISSION, "record_id": "copied-fixed-id", "observed_paragraphs": ["A", "B", "B", "C"]}


def assert_review_only(result: dict) -> None:
    assert result["decision"]["action"] == "ABSTAIN"
    assert result["selected_output"] is None
    assert result.get("selected_paragraphs") is None
    assert result["receipt"]["decision"] == result["decision"]
    assert result["receipt"]["selected_output_sha256"] is None


def test_arbitrary_and_copied_fictional_paragraphs_never_become_trusted():
    fictional = loads_json((ROOT / "fixtures/workflow_examples.json").read_text(encoding="utf-8"))[0]
    for payload in (OMISSION, DUPLICATE, fictional,
                    {**fictional, "record_id": "sample-omission"}):
        result = run_workflow(payload)
        assert result["request"]["candidates"]
        assert result["review_changes"]
        assert result["request"]["evidence"] == {"trusted_insertions": [], "trusted_identities": []}
        assert_review_only(result)


def test_matching_proposal_is_review_only_and_invented_text_is_rejected():
    matched = run_proposal({**OMISSION, "proposed_paragraphs": ["A", "B", "C"]})
    invented = run_proposal({**OMISSION, "proposed_paragraphs": ["A", "invented", "C"]})
    assert_review_only(matched)
    assert matched["adapter_status"] == "PROPOSAL_REVIEW_REQUIRED"
    assert matched["proposed_paragraphs"] == ["A", "B", "C"]
    assert_review_only(invented)
    assert invented["adapter_status"] == "PROPOSAL_REJECTED"


def test_batch_and_cli_do_not_select_caller_paragraphs(tmp_path):
    summary = run_batch([OMISSION, {**DUPLICATE, "record_id": "duplicate"}])
    assert summary["summary"] == {"records": 2, "automatic": 0, "unchanged": 0, "review_required": 2}
    assert all(item["selected_paragraphs"] is None for item in summary["results"])
    for command, payload in (("workflow", OMISSION),
                             ("proposal", {**OMISSION, "proposed_paragraphs": ["A", "B", "C"]})):
        incoming = tmp_path / f"{command}.json"
        incoming.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", "-m", "biosure.cli", command,
                                 "--input", str(incoming)], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert_review_only(json.loads(result.stdout))


def test_http_routes_withhold_even_copied_graph_evidence():
    graph = loads_json((ROOT / "fixtures/challenge/01-insertion-good.json").read_text(encoding="utf-8"))
    assert graph["evidence"]["trusted_insertions"]
    server = make_server(ROOT / "fixtures", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        for endpoint, payload in (("workflow", OMISSION),
                                  ("proposal", {**OMISSION, "proposed_paragraphs": ["A", "B", "C"]}),
                                  ("decide", graph)):
            request = urllib.request.Request(base + "/api/" + endpoint,
                data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                assert_review_only(json.load(response))
        request = urllib.request.Request(base + "/api/batch",
            data=json.dumps([OMISSION]).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.load(response)
        assert result["summary"]["automatic"] == 0
        assert_review_only(result["results"][0])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("untrusted", [
    {"source_url": "https://example.org/record"},
    {"source_sha256": "0" * 64},
    {"reference_acknowledged": True},
    {"trusted": True},
])
def test_extra_client_trust_claims_are_rejected(untrusted):
    with pytest.raises(ValueError, match="workflow requires"):
        run_workflow({**OMISSION, **untrusted})
