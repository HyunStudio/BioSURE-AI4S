"""The fixed fictional policy audit must expose forged-reference behavior."""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "fixtures/policy_boundary_inputs.json"
EXPECTED = ROOT / "fixtures/policy_boundary_expected.json"
FROZEN = ROOT / "results/policy_boundary_audit.json"
IDS = (
    "unsupported-replacement",
    "stale-reference-multiple-mismatches",
    "invented-upstream-wording",
    "url-digest-only-withheld-evidence",
    "supported-internal-omission",
    "forged-reference-exposure",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixed_inputs_and_expected_labels_are_separate():
    inputs, expected = load(INPUTS), load(EXPECTED)
    assert [case["case_id"] for case in inputs["cases"]] == list(IDS)
    assert [case["case_id"] for case in expected["cases"]] == list(IDS)
    assert all("expected_action" not in case and "classification" not in case
               for case in inputs["cases"])
    assert [case["classification"] for case in expected["cases"]] == ["contract"] * 5 + ["exposure"]
    assert "public" not in json.dumps(inputs).lower()


def test_decision_stage_runs_without_labels_and_binds_receipts():
    from scripts.evaluate_policy_boundary import decide_inputs

    decisions = decide_inputs(load(INPUTS))
    assert [case["case_id"] for case in decisions["cases"]] == list(IDS)
    assert [case["actual_action"] for case in decisions["cases"]] == [
        "ABSTAIN", "ABSTAIN", "ABSTAIN", "ABSTAIN", "ABSTAIN", "ABSTAIN"
    ]
    assert all(re.fullmatch(r"[0-9a-f]{64}", case["decision_receipt_sha256"])
               for case in decisions["cases"])
    assert decisions["cases"][2]["proposal_receipt_sha256"] is not None
    assert decisions["cases"][3]["trusted_insertions_count"] == 0
    assert "expected_action" not in json.dumps(decisions)


def test_scoring_reports_five_contract_checks_and_separate_exposure():
    from scripts.evaluate_policy_boundary import decide_inputs, score_decisions

    scored = score_decisions(decide_inputs(load(INPUTS)), load(EXPECTED))
    assert scored["contract_checks"] == 5
    assert scored["contract_passed"] == 5
    assert scored["exposure_controls"] == 1
    assert scored["exposure_auto_repairs"] == 0
    assert scored["cases"][-1]["classification"] == "exposure"
    assert scored["cases"][-1]["actual_action"] == "ABSTAIN"
    assert scored == load(FROZEN)


def test_malformed_inputs_and_stale_labels_fail_closed():
    from scripts.evaluate_policy_boundary import decide_inputs, score_decisions

    inputs = load(INPUTS)
    duplicated = copy.deepcopy(inputs)
    duplicated["cases"][1]["case_id"] = duplicated["cases"][0]["case_id"]
    with pytest.raises(ValueError, match="duplicate"):
        decide_inputs(duplicated)
    invalid_id = copy.deepcopy(inputs)
    invalid_id["cases"][0]["case_id"] = ["unsupported-replacement"]
    with pytest.raises(ValueError, match="case ID"):
        decide_inputs(invalid_id)
    unknown = copy.deepcopy(inputs)
    unknown["cases"][0]["entrypoint"] = "fictional-pass"
    with pytest.raises(ValueError, match="entrypoint"):
        decide_inputs(unknown)
    invalid_digest = copy.deepcopy(inputs)
    invalid_digest["cases"][3]["declared_digest"] = "Z" * 64
    with pytest.raises(ValueError, match="provenance"):
        decide_inputs(invalid_digest)
    expected = load(EXPECTED)
    expected["input_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest"):
        score_decisions(decide_inputs(inputs), expected)


def test_cli_verifies_frozen_result_without_rewriting_it():
    before = FROZEN.read_bytes()
    outcome = subprocess.run([sys.executable, "scripts/evaluate_policy_boundary.py", "verify", "--root", str(ROOT)],
                             cwd=ROOT, capture_output=True, text=True, check=False)
    assert outcome.returncode == 0, outcome.stderr
    assert json.loads(outcome.stdout) == {"contract_checks": 5, "contract_passed": 5,
                                          "exposure_auto_repairs": 0}
    assert FROZEN.read_bytes() == before


def test_frozen_policy_result_drift_is_rejected(tmp_path):
    from scripts.evaluate_policy_boundary import verify

    (tmp_path / "fixtures").mkdir()
    (tmp_path / "results").mkdir()
    for source in (INPUTS, EXPECTED, FROZEN):
        shutil.copyfile(source, tmp_path / source.parent.name / source.name)
    frozen = load(tmp_path / "results/policy_boundary_audit.json")
    frozen["contract_passed"] = 6
    (tmp_path / "results/policy_boundary_audit.json").write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen policy boundary audit mismatch"):
        verify(tmp_path)


def test_full_reproduction_reports_policy_contract_and_exposure():
    from scripts.verify_reproduction import verify

    result = verify(ROOT)["policy_boundary_audit"]
    assert result == {"contract_checks": 5, "contract_passed": 5, "exposure_auto_repairs": 0}


def test_no_prior_release_includes_policy_inputs_labels_and_frozen_result(tmp_path):
    from scripts.audit_release import audit
    from scripts.prepare_release import prepare, verify_manifest

    destination = tmp_path / "release"
    prepare(ROOT, destination)
    for name in ("fixtures/policy_boundary_inputs.json", "fixtures/policy_boundary_expected.json",
                 "results/policy_boundary_audit.json", "scripts/evaluate_policy_boundary.py"):
        assert (destination / name).is_file()
    verify_manifest(destination)
    assert audit(destination) == []
