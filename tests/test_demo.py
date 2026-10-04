from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.evaluate import decide_case
from biosure.web_demo import make_server
from biosure.workflow import run_workflow


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


@contextmanager
def running_demo():
    server = make_server(FIXTURES, "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def get_json(url: str, timeout: float = 20) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(base, endpoint, value, headers=None):
    request = urllib.request.Request(base + endpoint, data=json.dumps(value).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=4) as response:
        return json.load(response)


def test_actual_paragraph_input_uses_same_workflow_and_no_fixture_writes():
    source = {"record_id": "test", "reference_paragraphs": ["Alpha", "Beta", "Gamma"],
              "observed_paragraphs": ["Alpha", "Gamma"]}
    before = sorted(str(path) for path in FIXTURES.rglob("*"))
    with running_demo() as base:
        actual = post_json(base, "/api/workflow", source, {"Origin": base})
        assert actual == run_workflow(source)
        assert actual["selected_paragraphs"] == ["Alpha", "Beta", "Gamma"]
        assert "gold" not in actual
    assert sorted(str(path) for path in FIXTURES.rglob("*")) == before


def test_custom_decision_input_uses_the_same_receipt():
    source = json.loads((FIXTURES / "challenge/02-insertion-wrong-hash.json").read_text(encoding="utf-8"))
    with running_demo() as base:
        result = post_json(base, "/api/decide", source)
        assert result["decision"]["action"] == "ABSTAIN"
        assert result["receipt"] == decide_case(FIXTURES / "challenge/02-insertion-wrong-hash.json").receipt


@pytest.mark.parametrize("body,headers,status", [
    (b'{"record_id":"a","record_id":"b"}', {"Content-Type": "application/json"}, 400),
    (b'not JSON', {"Content-Type": "application/json"}, 400),
    (b'{}', {"Content-Type": "application/json", "Origin": "https://attacker.example"}, 403),
    (b'{}', {"Content-Type": "application/json", "Host": "attacker.example"}, 403),
    (b'{}', {"Content-Type": "text/plain"}, 415),
    (b'x' * (1048576 + 1), {"Content-Type": "application/json"}, 413),
    (b'{"gold":{}}', {"Content-Type": "application/json"}, 400),
], ids=["duplicate-key", "bad-json", "foreign-origin", "foreign-host", "content-type", "oversize", "unknown-field"])
def test_input_endpoint_rejects_unsafe_or_invalid_requests(body, headers, status):
    with running_demo() as base:
        request = urllib.request.Request(base + "/api/workflow", data=body, headers=headers)
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=4)
        assert caught.value.code == status
        assert "Alpha" not in caught.value.read().decode("utf-8")


def test_post_unknown_route_is_not_a_file_write():
    with running_demo() as base:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post_json(base, "/anything", {})
        assert caught.value.code == 404


def test_input_server_cannot_bind_public_interface():
    with pytest.raises(ValueError):
        make_server(FIXTURES, "0.0.0.0", 0)


def test_stress_dataset_includes_negative_control_in_summary():
    with running_demo() as base:
        # This test checks scoring, not NAS throughput. The source worktree
        # may be on a network drive; clean local archives are much faster.
        summary = get_json(base + "/api/summary?dataset=stress", timeout=60)
        assert (summary["cases"], summary["source_graphs"], summary["incorrect_auto"]) == (168, 12, 12)
        assert summary["by_condition"]["forged-evidence"]["incorrect_auto"] == 12


def test_demo_cases_call_the_same_gate() -> None:
    names = ["01-insertion-good", "02-insertion-wrong-hash", "06-insertion-ambiguous"]
    with running_demo() as base:
        listing = get_json(base + "/api/cases")
        assert len(listing["cases"]) == 8
        for name in names:
            actual = get_json(base + "/api/case/" + name)
            expected = decide_case(FIXTURES / "challenge" / (name + ".json"))
            assert actual["decision"]["action"] == expected.decision.action
            assert actual["decision"]["reason_codes"] == list(expected.decision.reason_codes)
            assert actual["receipt"]["receipt_sha256"] == expected.receipt["receipt_sha256"]
            assert "gold" not in json.dumps(actual)


def test_demo_serves_separate_public_and_dke_headings() -> None:
    with running_demo() as base:
        with urllib.request.urlopen(base + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
        assert "Public synthetic challenge" in html
        assert "DKE prior study" in html
        assert "Not clinical" in html
        summary = get_json(base + "/api/summary")
        assert summary["cases"] == 8
        assert summary["source_graphs"] == 2
        if (ROOT / "results/dke_prior_aggregate.json").is_file():
            prior = get_json(base + "/api/prior")
            assert prior["evidence_class"] == "unreproduced_article_level_prior"
            assert prior["held_out"] == 120
        else:
            with pytest.raises(urllib.error.HTTPError) as caught:
                get_json(base + "/api/prior")
            assert caught.value.code == 404


def test_demo_rejects_non_allowlisted_case() -> None:
    with running_demo() as base:
        try:
            urllib.request.urlopen(base + "/api/case/not-a-case", timeout=3)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("unknown case should return 404")


def test_article_dataset_is_selectable_and_scored_separately() -> None:
    with running_demo() as base:
        listing = get_json(base + "/api/cases?dataset=article")
        assert len(listing["cases"]) == 9
        assert listing["dataset"] == "article"
        summary = get_json(base + "/api/summary?dataset=article")
        assert (summary["cases"], summary["source_graphs"], summary["exact_auto"]) == (9, 3, 3)
        for suffix, action in (("good", "AUTO_REPAIR"), ("wrong-hash", "ABSTAIN"), ("no-evidence", "ABSTAIN")):
            name = "PMC5562747-" + suffix
            actual = get_json(base + "/api/case/" + name + "?dataset=article")
            expected = decide_case(FIXTURES / "article_challenge" / (name + ".json"))
            assert actual["decision"]["action"] == action
            assert actual["receipt"] == expected.receipt
            assert actual["source"]["pmcid"] == "PMC5562747"
            assert actual["source"]["article_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC5562747/"
            assert "gold" not in actual
        assert get_json(base + "/api/summary")["cases"] == 8


@pytest.mark.parametrize("query", ["dataset=../../gold", "dataset=unknown", "dataset=article&dataset=synthetic"])
def test_demo_rejects_invalid_dataset_selection(query: str) -> None:
    with running_demo() as base:
        with pytest.raises(urllib.error.HTTPError) as caught:
            get_json(base + "/api/cases?" + query)
        assert caught.value.code == 400


def test_article_dataset_cannot_open_synthetic_case() -> None:
    with running_demo() as base:
        with pytest.raises(urllib.error.HTTPError) as caught:
            get_json(base + "/api/case/01-insertion-good?dataset=article")
        assert caught.value.code == 404


def test_asset_rights_inventory_is_complete() -> None:
    rights = (ROOT / "RIGHTS.md").read_text(encoding="utf-8")
    assert "project-authored" in rights
    assert "fixtures/challenge" in rights
    assert "fixtures/gold" in rights
    assert "biosure/static" in rights


def test_browser_script_renders_both_distinct_candidates() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is optional for the browser-script test")
    script = r"""
const fs = require('fs');
const vm = require('vm');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const elements = new Map();
function element(tag) {
  return {
    tag, children: [], textContent: '', className: '', value: '',
    classList: { add() {} },
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    addEventListener() {},
  };
}
const document = {
  getElementById(id) { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); },
  createElement: element,
};
const data = {
  request: payload,
  decision: { action: 'ABSTAIN', reason_codes: ['AMBIGUOUS_CANDIDATES'] },
  receipt: { receipt_sha256: 'test-receipt', selected_output_sha256: null },
};
const fetch = (url) => url.startsWith('/api/case/')
  ? Promise.resolve({ ok: true, json: async () => data })
  : new Promise(() => {});
const context = vm.createContext({ document, fetch, Set, console });
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
context.loadCase('06-insertion-ambiguous').then(() => {
  function text(node) { return [node.textContent, ...node.children.map(text)].join(' '); }
  process.stdout.write(text(document.getElementById('candidate-list')));
}).catch((error) => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", script, str(ROOT / "biosure" / "static" / "app.js"), str(FIXTURES / "challenge" / "06-insertion-ambiguous.json")],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    assert "candidate-1" in result.stdout
    assert "candidate-2" in result.stdout
    assert "p4" in result.stdout


def test_workflow_browser_discards_stale_response_after_clear() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is optional for the browser-script test")
    script = r"""
const fs = require('fs'); const vm = require('vm'); const elements = new Map();
const make = () => ({value:'', textContent:'', disabled:false, checked:true,
  addEventListener(){}, replaceChildren(){}, removeAttribute(){}});
const document = {getElementById(id){if(!elements.has(id)) elements.set(id,make()); return elements.get(id);}};
let resolveFetch; const fetch = () => new Promise(resolve => {resolveFetch = resolve;});
const context = vm.createContext({document,fetch,JSON,console});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
document.getElementById('reference-input').value = 'Alpha\n\nBeta\n\nGamma';
document.getElementById('observed-input').value = 'Alpha\n\nGamma';
const pending = context.runParagraphCheck(); context.clearWorkflow();
resolveFetch({ok:true,json:async()=>({decision:{action:'AUTO_REPAIR',reason_codes:[]},
  adapter_status:'CANDIDATE_PROPOSED',selected_paragraphs:['Alpha','Beta','Gamma'],receipt:{receipt_sha256:'receipt'}})});
pending.then(()=>{
  if(document.getElementById('workflow-output').textContent !== '') throw Error('stale prose restored');
  if(!document.getElementById('download-result').disabled) throw Error('stale download restored');
  if(document.getElementById('workflow-status').textContent !== 'READY') throw Error('stale status restored');
}).catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(["node", "-e", script, str(ROOT / "biosure/static/workflow.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
