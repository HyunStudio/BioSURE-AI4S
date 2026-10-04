"""A locked audit must keep every selected attempt and separate decisions from gold."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from biosure.prospective_audit import evaluate_manifest, preflight_manifest


ROOT = Path(__file__).resolve().parents[1]
MODEL = json.loads((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))


def _put(root: Path, name: str, value: bytes | dict) -> str:
    data = json.dumps(value).encode("utf-8") if isinstance(value, dict) else value
    path = root / name
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _fixture(root: Path) -> dict:
    protocol_sha = _put(root, "protocol.md", b"Locked before inspection\n")
    inputs = {"schema_version": "biosure.native-pilot-inputs/1.0",
              "source": {"id": "PMC100", "license_uri": "https://creativecommons.org/licenses/by/4.0/"},
              "cases": [{"case_id": "PMC100-title", "source_locator": "article page 1 title",
                         "condition": "control", "reference_paragraphs": ["A title."],
                         "observed_paragraphs": ["A title."]}]}
    input_sha = _put(root, "inputs.json", inputs)
    _put(root, "gold.json", b"gold is deliberately unreadable during preflight\xff")
    return {"schema_version": "biosure.prospective-audit/1.0",
            "protocol_path": "protocol.md", "protocol_sha256": protocol_sha,
            "sources": [{"source_id": "PMC100", "split": "development", "doi": "10.1/one",
                         "pmcid": "PMC100", "license_uri": "https://creativecommons.org/licenses/by/4.0/",
                         "inputs_path": "inputs.json", "inputs_sha256": input_sha,
                         "gold_path": "gold.json", "gold_sha256": "0" * 64,
                         "units": [{"unit_id": "PMC100-title", "status": "scorable",
                                    "case_id": "PMC100-title"},
                                   {"unit_id": "PMC100-abstract", "status": "unscorable",
                                    "reason": "continues onto page two"}]}]}


def _good_fixture(root: Path) -> dict:
    manifest = _fixture(root)
    inputs = json.loads((root / "inputs.json").read_text(encoding="utf-8"))
    from biosure.schema import sha256
    gold = {"schema_version": "biosure.native-pilot-gold/1.0",
            "input_sha256": sha256(inputs),
            "cases": [{"case_id": "PMC100-title", "gold_paragraphs": ["A title."]}]}
    manifest["sources"][0]["gold_sha256"] = _put(root, "gold.json", gold)
    return manifest


def test_preflight_keeps_partial_source_and_does_not_open_gold(tmp_path):
    manifest = _fixture(tmp_path)
    sources = preflight_manifest(manifest, tmp_path)
    assert [source["source_id"] for source in sources] == ["PMC100"]
    assert len(sources[0]["units"]) == 2


def test_preflight_rejects_missing_file_before_any_evaluation(tmp_path):
    manifest = _fixture(tmp_path)
    manifest["sources"][0]["gold_path"] = "missing.json"
    with pytest.raises(ValueError, match="missing"):
        preflight_manifest(manifest, tmp_path)


def test_preflight_rejects_path_traversal(tmp_path):
    manifest = _fixture(tmp_path)
    manifest["sources"][0]["inputs_path"] = "../outside.json"
    with pytest.raises(ValueError, match="outside|relative|path"):
        preflight_manifest(manifest, tmp_path)


def test_preflight_rejects_duplicate_source_and_unit_ids(tmp_path):
    manifest = _fixture(tmp_path)
    manifest["sources"].append(dict(manifest["sources"][0]))
    with pytest.raises(ValueError, match="source ID"):
        preflight_manifest(manifest, tmp_path)
    manifest["sources"].pop()
    manifest["sources"][0]["units"][1]["unit_id"] = "PMC100-title"
    with pytest.raises(ValueError, match="unit ID"):
        preflight_manifest(manifest, tmp_path)


def test_preflight_rejects_duplicate_case_ids_in_input(tmp_path):
    manifest = _fixture(tmp_path)
    inputs = json.loads((tmp_path / "inputs.json").read_text(encoding="utf-8"))
    inputs["cases"].append(dict(inputs["cases"][0]))
    manifest["sources"][0]["inputs_sha256"] = _put(tmp_path, "inputs.json", inputs)
    with pytest.raises(ValueError, match="case ID"):
        preflight_manifest(manifest, tmp_path)


@pytest.mark.parametrize("field,value", [("split", "training"), ("status", "ignored")])
def test_preflight_rejects_invalid_split_or_unit_status(tmp_path, field, value):
    manifest = _fixture(tmp_path)
    target = manifest["sources"][0] if field == "split" else manifest["sources"][0]["units"][0]
    target[field] = value
    with pytest.raises(ValueError, match=field):
        preflight_manifest(manifest, tmp_path)


def test_preflight_rejects_unscorable_unit_without_reason(tmp_path):
    manifest = _fixture(tmp_path)
    del manifest["sources"][0]["units"][1]["reason"]
    with pytest.raises(ValueError, match="reason"):
        preflight_manifest(manifest, tmp_path)


@pytest.mark.parametrize("target", ["protocol", "input"])
def test_preflight_rejects_stale_digest(tmp_path, target):
    manifest = _fixture(tmp_path)
    if target == "protocol":
        manifest["protocol_sha256"] = "f" * 64
    else:
        manifest["sources"][0]["inputs_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="digest|SHA-256"):
        preflight_manifest(manifest, tmp_path)


def test_preflight_rejects_unit_case_mismatch(tmp_path):
    manifest = _fixture(tmp_path)
    manifest["sources"][0]["units"][0]["case_id"] = "wrong"
    with pytest.raises(ValueError, match="case"):
        preflight_manifest(manifest, tmp_path)


def test_evaluation_retains_zero_error_and_unscorable_attempts(tmp_path):
    manifest = _good_fixture(tmp_path)
    result = evaluate_manifest(manifest, tmp_path, MODEL)
    overall = result["summary"]["overall"]
    assert overall["attempted_sources"] == 1
    assert overall["scorable_sources"] == 1
    assert overall["attempted_units"] == 2
    assert overall["scorable_units"] == 1
    assert overall["native_error_cases"] == 0
    assert overall["unscorable"] == [{"source_id": "PMC100", "unit_id": "PMC100-abstract",
                                      "reason": "continues onto page two"}]
    assert overall["biosure"]["exact_auto"] == 0
    assert overall["direct_copy"]["exact_auto"] == 1
    assert overall["diff_review"]["manual_review_records"] == 0
    assert len(result["decisions"]) == 1


def test_evaluation_split_totals_include_fully_unscorable_source(tmp_path):
    manifest = _good_fixture(tmp_path)
    manifest["sources"].append({"source_id": "PMC200", "split": "held_out", "doi": "10.1/two",
                                "pmcid": "PMC200", "license_uri": "https://creativecommons.org/licenses/by/4.0/",
                                "units": [{"unit_id": "PMC200-title", "status": "unscorable",
                                           "reason": "PDF could not be acquired"}]})
    summary = evaluate_manifest(manifest, tmp_path, MODEL)["summary"]
    assert summary["overall"]["attempted_sources"] == 2
    assert summary["overall"]["attempted_units"] == 3
    assert summary["development"]["scorable_units"] == 1
    assert summary["held_out"]["attempted_units"] == 1
    assert summary["held_out"]["scorable_units"] == 0
    assert summary["held_out"]["biosure"]["incorrect_auto"] == 0


def test_evaluation_finishes_all_decisions_before_reading_any_gold(tmp_path):
    manifest = _fixture(tmp_path)  # first gold is not valid JSON
    second = dict(manifest["sources"][0])
    second["source_id"] = second["pmcid"] = "PMC200"
    second["doi"] = "10.1/two"
    second["units"] = [{"unit_id": "PMC200-title", "status": "scorable", "case_id": "PMC200-title"}]
    second["inputs_path"] = "inputs2.json"
    second["gold_path"] = "gold2.json"
    inputs = json.loads((tmp_path / "inputs.json").read_text(encoding="utf-8"))
    inputs["source"]["id"] = "PMC200"
    inputs["cases"][0]["case_id"] = "PMC200-title"
    inputs["cases"][0]["unsupported"] = True  # preflight accepts ID; decision must reject schema
    second["inputs_sha256"] = _put(tmp_path, "inputs2.json", inputs)
    _put(tmp_path, "gold2.json", b"also invalid")
    manifest["sources"].append(second)
    with pytest.raises(ValueError, match="pilot case fields"):
        evaluate_manifest(manifest, tmp_path, MODEL)


def test_evaluation_rejects_gold_digest_mismatch_after_decisions(tmp_path):
    manifest = _good_fixture(tmp_path)
    manifest["sources"][0]["gold_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="gold digest"):
        evaluate_manifest(manifest, tmp_path, MODEL)


def test_cli_writes_fresh_decisions_and_summary_without_overwriting(tmp_path):
    manifest = _good_fixture(tmp_path)
    _put(tmp_path, "manifest.json", manifest)
    output = tmp_path / "audit-output"
    command = [sys.executable, str(ROOT / "scripts/evaluate_prospective_audit.py"),
               "--manifest", str(tmp_path / "manifest.json"),
               "--model", str(ROOT / "fixtures/ml_model.json"), "--out-dir", str(output)]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert json.loads((output / "summary.json").read_text(encoding="utf-8"))["overall"]["attempted_units"] == 2
    assert json.loads((output / "decisions.json").read_text(encoding="utf-8"))[0]["source_id"] == "PMC100"
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert "exists" in second.stderr


def test_cli_does_not_create_output_when_gold_is_invalid(tmp_path):
    manifest = _fixture(tmp_path)
    _put(tmp_path, "manifest.json", manifest)
    output = tmp_path / "failed-output"
    command = [sys.executable, str(ROOT / "scripts/evaluate_prospective_audit.py"),
               "--manifest", str(tmp_path / "manifest.json"),
               "--model", str(ROOT / "fixtures/ml_model.json"), "--out-dir", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not output.exists()
