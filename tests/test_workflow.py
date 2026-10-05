from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.workflow import run_workflow


def payload(observed=None, reference=None):
    return {"record_id": "conversion-check", "reference_paragraphs": reference or ["Alpha", "Beta", "Gamma"],
            "observed_paragraphs": observed if observed is not None else ["Alpha", "Gamma"]}


def test_internal_omission_proposes_but_does_not_select_unverified_text():
    source = payload()
    original = copy.deepcopy(source)
    result = run_workflow(source)
    assert result["decision"]["action"] == "ABSTAIN"
    assert result["selected_paragraphs"] is None
    assert result["request"]["evidence"]["trusted_insertions"] == []
    assert result["request"]["candidates"][0]["operation"] == "INSERT_PARAGRAPH"
    assert result["adapter_status"] == "CANDIDATE_PROPOSED"
    assert source == original
    assert run_workflow(source) == result
    assert "gold" not in result


def test_exact_extra_duplicate_is_proposed_but_not_applied():
    result = run_workflow(payload(["Alpha", "Beta", "Beta", "Gamma"]))
    assert result["decision"]["action"] == "ABSTAIN"
    assert result["request"]["candidates"][0]["operation"] == "REMOVE_DUPLICATE"
    assert result["selected_paragraphs"] is None
    repeated = run_workflow(payload(["Alpha", "Beta", "Gamma"], ["Alpha", "Beta", "Beta", "Gamma"]))
    assert repeated["adapter_status"] == "AMBIGUOUS_REFERENCE"
    assert repeated["decision"]["action"] == "ABSTAIN"
    assert repeated["selected_paragraphs"] is None


def test_nonadjacent_duplicate_before_original_remains_review_only():
    result = run_workflow(payload(["Alpha", "Gamma", "Beta", "Gamma"]))
    assert result["decision"]["action"] == "ABSTAIN"
    assert result["selected_paragraphs"] is None


@pytest.mark.parametrize("observed,status", [
    (["Alpha", "Beta", "Gamma"], "NO_CHANGE"),
    (["Alpha", "Wrong", "Gamma"], "UNSUPPORTED_DIFFERENCE"),
    (["Gamma", "Alpha", "Beta"], "UNSUPPORTED_DIFFERENCE"),
    (["Alpha"], "UNSUPPORTED_DIFFERENCE"),
    (["Beta", "Gamma"], "BOUNDARY_OMISSION"),
    (["Alpha", "Beta"], "BOUNDARY_OMISSION"),
])
def test_unsupported_or_unchanged_input_is_not_applied(observed, status):
    result = run_workflow(payload(observed))
    assert result["adapter_status"] == status
    assert result["decision"]["action"] == "ABSTAIN"
    assert result["selected_paragraphs"] is None


def test_normalization_and_reference_hash_track_actual_input():
    result = run_workflow(payload([" Alpha \n ", "Gamma"]))
    assert result["selected_paragraphs"] is None
    changed = run_workflow(payload(reference=["Alpha", "Changed", "Gamma"]))
    assert result["reference_sha256"] != changed["reference_sha256"]
    assert result["request"]["candidates"][0]["document"] != changed["request"]["candidates"][0]["document"]


@pytest.mark.parametrize("change", [
    {"gold": {}}, {"reference_paragraphs": []}, {"reference_paragraphs": [""]},
    {"observed_paragraphs": "not a list"}, {"record_id": None},
    {"reference_paragraphs": ["X" * 4097]}, {"observed_paragraphs": ["X"] * 129},
    {"reference_paragraphs": [False]},
])
def test_invalid_input_rejected_without_silent_truncation(change):
    with pytest.raises(ValueError):
        run_workflow({**payload(), **change})


def test_total_text_limit_rejected():
    with pytest.raises(ValueError):
        run_workflow(payload(["X" * 4096] * 65, ["Y" * 4096] * 65))


def test_cli_workflow_calls_same_adapter(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload()), encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "biosure.cli", "workflow", "--input", str(path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == run_workflow(payload())


def test_cli_rejects_duplicate_reference_fields(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('{"record_id":"x","reference_paragraphs":["Alpha","Beta","Gamma"],'
                    '"reference_paragraphs":["Alpha","Forged","Gamma"],"observed_paragraphs":["Alpha","Gamma"]}', encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "biosure.cli", "workflow", "--input", str(path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ""
