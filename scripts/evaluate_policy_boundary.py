"""Replay fictional policy controls without calling them source authentication."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.schema import loads_json, sha256
from biosure.workflow import run_proposal, run_workflow


CASE_IDS = (
    "unsupported-replacement",
    "stale-reference-multiple-mismatches",
    "invented-upstream-wording",
    "url-digest-only-withheld-evidence",
    "supported-internal-omission",
    "forged-reference-exposure",
)
SCOPE = ("Five fictional policy contracts plus one separately reported forged-reference control; "
         "public adapters abstain without source authentication. No biological truth, user benefit "
         "or model superiority is tested.")


def _read(path: Path) -> dict:
    value = loads_json(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("policy audit JSON must be an object")
    return value


def decide_inputs(inputs: dict) -> dict:
    """Decide all cases with no expected outcomes in the call or input schema."""
    if not isinstance(inputs, dict) or set(inputs) != {"schema_version", "scope", "cases"} or (
        inputs["schema_version"] != "biosure.policy-boundary-inputs/1.0"
    ) or not isinstance(inputs["scope"], str) or not isinstance(inputs["cases"], list):
        raise ValueError("invalid policy inputs")
    cases = inputs["cases"]
    if len(cases) != len(CASE_IDS):
        raise ValueError("policy audit requires all six cases")
    ids = [case.get("case_id") if isinstance(case, dict) else None for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids):
        raise ValueError("invalid policy case ID")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate policy case ID")
    if tuple(ids) != CASE_IDS:
        raise ValueError("unexpected policy case IDs or order")
    decided = []
    for case in cases:
        entrypoint = case.get("entrypoint")
        base_fields = {"case_id", "entrypoint", "input"}
        if entrypoint == "withheld-evidence":
            if set(case) != base_fields | {"declared_url", "declared_digest"} or (
                not isinstance(case["declared_url"], str) or
                not case["declared_url"].startswith("https://") or
                not isinstance(case["declared_digest"], str) or
                re.fullmatch(r"[0-9a-f]{64}", case["declared_digest"]) is None
            ):
                raise ValueError("invalid unverified provenance declaration")
        elif entrypoint in {"workflow", "proposal"}:
            if set(case) != base_fields:
                raise ValueError("invalid policy case fields")
        else:
            raise ValueError("unknown policy entrypoint")
        payload = case["input"]
        if not isinstance(payload, dict) or payload.get("record_id") != case["case_id"]:
            raise ValueError("policy case record mismatch")
        preflight = "none"
        if entrypoint == "workflow":
            result = run_workflow(payload)
        elif entrypoint == "proposal":
            result = run_proposal(payload)
        else:
            # A declared URL/digest cannot authenticate the submitted text.
            # The public adapter itself withholds trust even for a candidate.
            result = run_workflow(payload)
            if not result["request"]["candidates"]:
                raise ValueError("withheld-evidence control requires an actual candidate")
            preflight = "public-adapter-withheld-unverified-evidence"
        decided.append({
            "case_id": case["case_id"],
            "actual_action": result["decision"]["action"],
            "reason_codes": result["decision"]["reason_codes"],
            "decision_receipt_sha256": result["receipt"]["receipt_sha256"],
            "proposal_receipt_sha256": (
                result["proposal_receipt"]["receipt_sha256"] if entrypoint == "proposal" else None
            ),
            "selected_output_sha256": result["receipt"]["selected_output_sha256"],
            "trusted_insertions_count": len(result["request"]["evidence"]["trusted_insertions"]),
            "caller_preflight": preflight,
        })
    return {"schema_version": "biosure.policy-boundary-decisions/1.0",
            "input_sha256": sha256(cases), "cases": decided}


def score_decisions(decisions: dict, expected: dict) -> dict:
    """Open expected labels only after the decision bundle exists."""
    if not isinstance(decisions, dict) or set(decisions) != {"schema_version", "input_sha256", "cases"} or (
        decisions["schema_version"] != "biosure.policy-boundary-decisions/1.0"
    ) or not isinstance(decisions["cases"], list):
        raise ValueError("invalid policy decisions")
    if not isinstance(expected, dict) or set(expected) != {"schema_version", "input_sha256", "cases"} or (
        expected["schema_version"] != "biosure.policy-boundary-expected/1.0"
    ) or expected["input_sha256"] != decisions["input_sha256"]:
        raise ValueError("policy expected digest mismatch")
    labels = expected["cases"]
    if not isinstance(labels, list) or len(labels) != len(CASE_IDS) or len(decisions["cases"]) != len(CASE_IDS):
        raise ValueError("invalid policy expected case count")
    scored = []
    for index, (actual, label) in enumerate(zip(decisions["cases"], labels)):
        if (not isinstance(actual, dict) or not isinstance(label, dict) or
            set(label) != {"case_id", "classification", "expected_action", "expected_reason_codes"} or
            actual.get("case_id") != CASE_IDS[index] or label["case_id"] != CASE_IDS[index] or
            label["classification"] != ("exposure" if index == 5 else "contract") or
            label["expected_action"] not in {"ABSTAIN", "AUTO_REPAIR"} or
            not isinstance(label["expected_reason_codes"], list)):
            raise ValueError("invalid policy expected labels")
        match = (actual["actual_action"] == label["expected_action"] and
                 actual["reason_codes"] == label["expected_reason_codes"])
        scored.append({**actual, "classification": label["classification"],
                       "expected_action": label["expected_action"],
                       "expected_reason_codes": label["expected_reason_codes"],
                       "matches_frozen_expectation": match})
    contracts = scored[:5]
    exposure = scored[5]
    return {"schema_version": "biosure.policy-boundary-audit/1.0",
            "input_sha256": decisions["input_sha256"], "scope": SCOPE,
            "contract_checks": len(contracts),
            "contract_passed": sum(case["matches_frozen_expectation"] for case in contracts),
            "exposure_controls": 1,
            "exposure_auto_repairs": int(exposure["actual_action"] == "AUTO_REPAIR"),
            "cases": scored}


def verify(root: Path) -> dict:
    root = root.resolve()
    inputs = _read(root / "fixtures/policy_boundary_inputs.json")
    decisions = decide_inputs(inputs)
    expected = _read(root / "fixtures/policy_boundary_expected.json")
    scored = score_decisions(decisions, expected)
    frozen = _read(root / "results/policy_boundary_audit.json")
    if scored != frozen or scored["contract_passed"] != 5 or scored["exposure_auto_repairs"] != 0:
        raise ValueError("frozen policy boundary audit mismatch")
    return {key: scored[key] for key in ("contract_checks", "contract_passed", "exposure_auto_repairs")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay the fixed fictional policy-boundary audit")
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.root), sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"policy audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
