"""A locked audit must keep every selected attempt and separate decisions from gold."""

import hashlib
import json
from pathlib import Path

import pytest

from biosure.prospective_audit import preflight_manifest


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
