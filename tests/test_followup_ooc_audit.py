"""Frozen two-source audit: new deposits must replay without model or gate tuning."""

from pathlib import Path

import pytest

from biosure.learned_upstream_audit import FOLLOWUP_LOCKED_SOURCES, evaluate_upstream_manifest
from biosure.prospective_audit import evaluate_manifest, preflight_manifest
from biosure.schema import loads_json


ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = (
    ("PMC12715219", "10.1038/s41598-025-30612-2"),
    ("PMC12707140", "10.1128/iai.00346-25"),
)


def test_followup_lock_and_rights_are_explicit():
    protocol = (ROOT / "report/followup-ooc-audit-protocol.md").read_text(encoding="utf-8")
    rights = (ROOT / "RIGHTS.md").read_text(encoding="utf-8")
    manifest = loads_json((ROOT / "fixtures/followup_ooc_manifest.json").read_text(encoding="utf-8"))
    assert [(source["source_id"], source["doi"]) for source in manifest["sources"]] == list(IDENTITIES)
    assert all(source["split"] == "held_out" for source in manifest["sources"])
    assert all(len(source["units"]) == 2 for source in manifest["sources"])
    for pmcid, doi in IDENTITIES:
        assert pmcid in protocol and doi in protocol and pmcid in rights and doi in rights
        fixture = loads_json((ROOT / f"fixtures/followup_ooc_{pmcid}_inputs.json").read_text(encoding="utf-8"))
        source = fixture["source"]
        assert source["id"] == pmcid and source["doi"] == doi
        assert source["license_uri"] == "https://creativecommons.org/licenses/by/4.0/"
        assert len(source["pdf_sha256"]) == len(source["xml_sha256"]) == 64
    preflight_manifest(manifest, ROOT)


def test_followup_frozen_replays_match_all_source_results():
    manifest = loads_json((ROOT / "fixtures/followup_ooc_manifest.json").read_text(encoding="utf-8"))
    model = loads_json((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    measured = evaluate_manifest(manifest, ROOT, model)
    expected = loads_json((ROOT / "results/followup_ooc_audit.json").read_text(encoding="utf-8"))
    decisions = loads_json((ROOT / "results/followup_ooc_decisions.json").read_text(encoding="utf-8"))
    assert measured["summary"] == expected
    assert measured["decisions"] == decisions
    learned = evaluate_upstream_manifest(manifest, ROOT, model,
                                         locked_sources=FOLLOWUP_LOCKED_SOURCES)
    frozen_learned = loads_json((ROOT / "results/followup_learned_upstream_audit.json").read_text(encoding="utf-8"))
    assert learned == frozen_learned
    assert expected["overall"]["attempted_sources"] == 2
    assert expected["overall"]["attempted_units"] == 4
    with pytest.raises(ValueError, match="unrecognized source-order lock"):
        evaluate_upstream_manifest(manifest, ROOT, model, locked_sources=(("PMC12715219", "development"),))
