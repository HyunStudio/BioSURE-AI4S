"""Constructed verified-source replay: fail-closed mechanics, not authentication."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.schema import loads_json, parse_request
from scripts import evaluate_verified_constructed as evc

ROOT = Path(__file__).resolve().parents[1]


def requests(root=ROOT):
    return [parse_request(loads_json(path.read_text(encoding="utf-8")))
            for path in sorted((root / "fixtures/stress_challenge").glob("*.json"))]


def sources():
    return [evc.source_document(index) for index in range(1, evc.SOURCE_COUNT + 1)]


def test_frozen_result_replays_and_has_no_incorrect_repair():
    assert evc.main(["verify", "--root", str(ROOT)]) == 0
    frozen = loads_json((ROOT / "results/verified_constructed_stress.json").read_text(encoding="utf-8"))
    verified = frozen["arms"]["verified_source"]
    assert (verified["exact_auto"], verified["incorrect_auto"], verified["abstentions"]) == (48, 0, 120)
    assert verified["by_condition"]["forged-evidence"]["automatic"] == 0
    public = frozen["arms"]["public_caller_evidence_gate"]
    assert (public["exact_auto"], public["incorrect_auto"]) == (24, 12)


def test_decisions_need_no_gold(tmp_path):
    shutil.copytree(ROOT / "fixtures/stress_challenge", tmp_path / "fixtures/stress_challenge")
    decided = evc._arm(requests(tmp_path), evc.ConstructedEnvelopeProvider(sources()))
    assert sum(item["action"] == "AUTO_REPAIR" for item in decided) == 48


def test_missing_or_stale_provider_abstains_everywhere():
    for provider in (None, evc.ConstructedEnvelopeProvider(sources(), "stale-version")):
        assert all(item["action"] == "ABSTAIN" for item in evc._arm(requests(), provider))


def test_provider_serving_the_forged_candidate_is_the_trust_assumption():
    """If the operator's source itself is the forged graph, selection follows it.

    This documents the assumption explicitly: the path checks consistency with the
    configured source, it does not authenticate that source.
    """
    forged = [r for r in requests() if r.case_id == "s01--forged-evidence"][0]
    provider = evc.ConstructedEnvelopeProvider([forged.candidates[0].document.to_mapping()])
    assert evc._arm([forged], provider)[0]["action"] == "AUTO_REPAIR"


def test_run_never_overwrites(tmp_path):
    out = tmp_path / "result.json"
    out.write_text("keep", encoding="utf-8")
    assert evc.main(["run", "--root", str(ROOT), "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "keep"
