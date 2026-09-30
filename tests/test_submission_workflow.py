"""User-visible triage behavior, not semantic or reference-truth validation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.workflow import run_workflow


def item(name="omission", observed=None):
    return {"record_id": name, "reference_paragraphs": ["Alpha", "Beta", "Gamma"],
            "observed_paragraphs": observed if observed is not None else ["Alpha", "Gamma"]}


@pytest.mark.parametrize("observed,kind,reference_span,observed_span,action", [
    (["Alpha", "Gamma"], "missing", [1, 2], [1, 1], "AUTO_REPAIR"),
    (["Alpha", "Beta", "Beta", "Gamma"], "extra", [2, 2], [2, 3], "AUTO_REPAIR"),
    (["Alpha", "Wrong", "Gamma"], "changed", [1, 2], [1, 2], "ABSTAIN"),
])
def test_review_hunks_are_literal_spans_and_do_not_override_gate(observed, kind, reference_span, observed_span, action):
    result = run_workflow(item(observed=observed))
    assert result["decision"]["action"] == action
    assert result["review_changes"] == [{"kind": kind, "reference_span": reference_span,
                                         "observed_span": observed_span}]


def test_whitespace_normalization_alone_has_no_review_changes():
    result = run_workflow(item(observed=[" Alpha \n", "Beta", "Gamma"]))
    assert result["review_changes"] == []
    assert result["adapter_status"] == "NO_CHANGE"


def test_duplicate_preview_identifies_the_copy_actually_removed_by_candidate():
    source = {"record_id": "duplicate", "reference_paragraphs": ["Header", "Methods", "Results", "Closing"],
              "observed_paragraphs": ["Header", "Methods", "Methods", "Results", "Closing"]}
    result = run_workflow(source)
    assert result["review_changes"] == [{"kind": "extra", "reference_span": [2, 2], "observed_span": [2, 3]}]
    damaged_ids = [b["block_id"] for b in result["request"]["damaged"]["blocks"]]
    selected_ids = [b["block_id"] for b in result["selected_output"]["blocks"]]
    assert damaged_ids[2] not in selected_ids


def test_batch_triages_changed_unchanged_and_review_without_rewriting_inputs():
    from biosure.batch import run_batch
    source = [item(), item("same", ["Alpha", "Beta", "Gamma"]), item("review", ["Alpha", "Wrong", "Gamma"])]
    before = json.dumps(source)
    result = run_batch(source)
    assert result["summary"] == {"records": 3, "automatic": 1, "unchanged": 1, "review_required": 1}
    assert [r["request"]["damaged"]["record_id"] for r in result["results"]] == ["omission", "same", "review"]
    assert result["results"][2]["selected_paragraphs"] is None
    assert json.dumps(source) == before


@pytest.mark.parametrize("source", [[], [item()] * 101, [item(), item()], [item(), {"record_id": "bad"}], {}])
def test_batch_rejects_invalid_records_and_duplicate_ids(source):
    from biosure.batch import run_batch
    with pytest.raises(ValueError):
        run_batch(source)


def cli(tmp_path, records, existing=False):
    incoming, outgoing = tmp_path / "input.json", tmp_path / "results.json"
    incoming.write_text(json.dumps(records), encoding="utf-8")
    if existing:
        outgoing.write_text("keep this", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "biosure.cli", "batch", "--input", str(incoming),
                             "--out", str(outgoing)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    return result, incoming, outgoing


def test_batch_cli_writes_explicit_output_after_all_records_validate(tmp_path):
    result, incoming, outgoing = cli(tmp_path, [item()])
    assert result.returncode == 0, result.stderr
    assert json.loads(outgoing.read_text(encoding="utf-8"))["summary"]["automatic"] == 1
    assert json.loads(incoming.read_text(encoding="utf-8")) == [item()]


def test_batch_cli_never_overwrites_existing_output(tmp_path):
    result, _, outgoing = cli(tmp_path, [item()], existing=True)
    assert result.returncode == 2
    assert result.stderr.startswith("BioSURE input error:")
    assert outgoing.read_text(encoding="utf-8") == "keep this"


def test_invalid_later_batch_record_leaves_no_partial_file(tmp_path):
    result, _, outgoing = cli(tmp_path, [item(), {"record_id": "bad"}])
    assert result.returncode == 2
    assert result.stderr.startswith("BioSURE input error:")
    assert not outgoing.exists()
