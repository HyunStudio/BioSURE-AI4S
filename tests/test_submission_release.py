from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_offline_verifier_checks_all_frozen_sets_and_literal_text_workflows():
    from scripts.verify_reproduction import verify
    report = verify(ROOT)
    assert report["passed"] is True
    assert report["sets"]["synthetic"] == {"cases": 8, "sources": 2, "exact": 2, "incorrect": 0, "abstentions": 6}
    assert report["sets"]["article"] == {"cases": 9, "sources": 3, "exact": 3, "incorrect": 0, "abstentions": 6}
    assert report["sets"]["stress"] == {"cases": 168, "sources": 12, "exact": 24, "incorrect": 12, "abstentions": 132}
    assert report["workflow_examples"] == {"records": 6, "automatic": 2, "unchanged": 1, "review_required": 3}


def test_frozen_result_drift_is_failure_not_silent_regeneration(tmp_path):
    from scripts.verify_reproduction import verify
    shutil.copytree(ROOT / "fixtures", tmp_path / "fixtures")
    (tmp_path / "results").mkdir()
    value = json.loads((ROOT / "results/stress_summary.json").read_text(encoding="utf-8"))
    value["incorrect_auto"] = 0
    (tmp_path / "results/stress_summary.json").write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="stress frozen summary mismatch"):
        verify(tmp_path)


def approved_source(path):
    from test_release import clean_package
    path.mkdir()
    clean_package(path)
    provenance = path / "fixtures/provenance.json"
    value = json.loads(provenance.read_text(encoding="utf-8"))
    value["asset_groups"].append({"pattern": "results/*.json", "origin": "authored test output",
                                  "rights": "test rights", "review_status": "approved_for_public_release"})
    value["asset_groups"].append({"pattern": "report/*.md", "origin": "authored test documents",
                                  "rights": "test rights", "review_status": "approved_for_public_release"})
    provenance.write_text(json.dumps(value), encoding="utf-8")
    (path / "report").mkdir()
    (path / "report/public-readme.md").write_text("# BioSURE\n", encoding="utf-8")
    (path / "report/public-rights.md").write_text("# Authored source inventory\n", encoding="utf-8")
    (path / "biosure/legacy_benchmark.py").write_text("DO NOT EXPORT THIS COPY", encoding="utf-8")
    (path / "results").mkdir()
    (path / "results/dke_prior_aggregate.json").write_text("{}", encoding="utf-8")
    return path


def test_release_profile_excludes_prior_code_and_data_and_binds_files(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    destination = tmp_path / "release"
    manifest = prepare(source, destination)
    assert not (destination / "biosure/legacy_benchmark.py").exists()
    assert not (destination / "results/dke_prior_aggregate.json").exists()
    assert (destination / "README.md").read_text(encoding="utf-8") == "# BioSURE\n"
    assert len(manifest["files"]["README.md"]) == 64
    assert manifest["profile"] == "biosure-public-no-prior-v1"
    from scripts.prepare_release import verify_manifest
    verify_manifest(destination)
    (destination / "README.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_manifest(destination)


def test_export_relocates_readme_links_to_existing_public_reports(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    (source / "report/public-submission.md").write_text("# Report", encoding="utf-8")
    (source / "report/public-readme.md").write_text("[report](public-submission.md) [rights](../RIGHTS.md)", encoding="utf-8")
    provenance = source / "fixtures/provenance.json"
    value = json.loads(provenance.read_text(encoding="utf-8"))
    value["asset_groups"].append({"pattern": "report/*.md", "origin": "authored test report",
                                  "rights": "test rights", "review_status": "approved_for_public_release"})
    provenance.write_text(json.dumps(value), encoding="utf-8")
    destination = tmp_path / "release"
    prepare(source, destination)
    assert (destination / "report/public-submission.md").is_file()
    assert (destination / "RIGHTS.md").is_file()
    from scripts.audit_release import audit
    assert audit(destination) == []


def test_standalone_profile_can_reexport_without_private_checkout_templates(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    first, second = tmp_path / "first", tmp_path / "second"
    prepare(source, first)
    prepare(first, second)
    assert (second / "README.md").read_bytes() == (first / "README.md").read_bytes()


def test_unapproved_rights_make_no_release_directory(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    provenance = source / "fixtures/provenance.json"
    value = json.loads(provenance.read_text(encoding="utf-8"))
    value["asset_groups"][0]["review_status"] = "pending_owner_review"
    provenance.write_text(json.dumps(value), encoding="utf-8")
    destination = tmp_path / "release"
    with pytest.raises(ValueError, match="rights approval"):
        prepare(source, destination)
    assert not destination.exists()


def test_existing_release_is_not_overwritten(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    destination = tmp_path / "release"
    destination.mkdir()
    marker = destination / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        prepare(source, destination)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_content_manifest_survives_clone_metadata_but_detects_extra_source_file(tmp_path):
    from scripts.prepare_release import prepare, verify_manifest
    source = approved_source(tmp_path / "source")
    destination = tmp_path / "release"
    prepare(source, destination)
    (destination / ".git").mkdir()
    (destination / ".git/config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
    verify_manifest(destination)
    (destination / "unexpected.txt").write_text("must not be silently ignored", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_manifest(destination)


def test_local_preview_discloses_pending_rights_without_approving_them(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    provenance = source / "fixtures/provenance.json"
    value = json.loads(provenance.read_text(encoding="utf-8"))
    value["asset_groups"][0]["review_status"] = "pending_owner_review"
    provenance.write_text(json.dumps(value), encoding="utf-8")
    before = provenance.read_bytes()
    manifest = prepare(source, tmp_path / "preview", local_preview=True)
    assert manifest["cleared_for_public_release"] is False
    assert any("rights approval" in f for f in manifest["audit_findings"])
    assert provenance.read_bytes() == before


def test_local_preview_still_blocks_security_findings(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    (source / "report/public-readme.md").write_text("sk-" + "testsecret1234567890123456", encoding="utf-8")
    with pytest.raises(ValueError, match="credential"):
        prepare(source, tmp_path / "preview", local_preview=True)
    assert not (tmp_path / "preview").exists()


def test_export_cannot_write_inside_source_tree(tmp_path):
    from scripts.prepare_release import prepare
    source = approved_source(tmp_path / "source")
    with pytest.raises(ValueError, match="outside source"):
        prepare(source, source / "nested")
    assert not (source / "nested").exists()


def test_public_cli_does_not_import_excluded_prior_code(tmp_path):
    shutil.copytree(ROOT / "biosure", tmp_path / "biosure", ignore=shutil.ignore_patterns("legacy.py", "legacy_benchmark.py", "__pycache__"))
    result = subprocess.run([sys.executable, "-m", "biosure.cli", "demo", "--case",
                             str(ROOT / "fixtures/challenge/01-insertion-good.json")],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"]["action"] == "AUTO_REPAIR"
    prior = subprocess.run([sys.executable, "-m", "biosure.cli", "legacy-demo"], cwd=tmp_path, capture_output=True, text=True)
    assert prior.returncode == 2
    assert prior.stderr.startswith("BioSURE input error:")


def test_missing_prior_is_explicitly_not_included_not_a_server_failure(tmp_path):
    from biosure.web_demo import make_server
    server = make_server(tmp_path / "fixtures", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/prior", timeout=3)
        assert caught.value.code == 404
        assert json.loads(caught.value.read())["included"] is False
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
