from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_release import audit


def clean_package(tmp_path: Path) -> Path:
    (tmp_path / "biosure").mkdir()
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "README.md").write_text("# Test package\n", encoding="utf-8")
    (tmp_path / "RIGHTS.md").write_text("# Project-authored assets\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Apache License Version 2.0\n", encoding="utf-8")
    provenance = {
        "schema_version": "biosure.synthetic-provenance/1.0",
        "author": "project-authored",
        "rights": "project-authored test package",
        "asset_groups": [{"pattern": pattern, "origin": "project-authored", "rights": "test rights", "review_status": "approved_for_public_release"} for pattern in (
            "README.md", "RIGHTS.md", "LICENSE", "fixtures/provenance.json", "biosure/*.py"
        )],
    }
    (tmp_path / "fixtures" / "provenance.json").write_text(json.dumps(provenance) + "\n", encoding="utf-8")
    (tmp_path / "biosure" / "__init__.py").write_text("", encoding="utf-8")
    return tmp_path


def test_clean_allowlisted_package_passes(tmp_path: Path) -> None:
    assert audit(clean_package(tmp_path)) == []


def ci_package(tmp_path: Path) -> Path:
    root = clean_package(tmp_path)
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/ci.yml").write_text("name: Verification\non: [push]\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / ".gitattributes").write_text("* text eol=lf\n", encoding="utf-8")
    provenance = root / "fixtures/provenance.json"
    data = json.loads(provenance.read_text(encoding="utf-8"))
    for name in (".gitignore", ".gitattributes", ".github/workflows/ci.yml"):
        data["asset_groups"].append({"pattern": name, "origin": "authored test configuration",
                                   "rights": "test rights", "review_status": "approved_for_public_release"})
    provenance.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_fixed_ci_and_ignore_config_allowed_but_arbitrary_workflow_rejected(tmp_path):
    root = ci_package(tmp_path)
    assert audit(root) == []
    (root / ".github/workflows/unknown.yml").write_text("name: Unknown", encoding="utf-8")
    assert any("non-allowlisted file: .github/workflows/unknown.yml" == finding for finding in audit(root))


def test_ci_yaml_credentials_are_not_exempt_from_scan(tmp_path):
    root = ci_package(tmp_path)
    (root / ".github/workflows/ci.yml").write_text("token: sk-" + "testsecret1234567890123456", encoding="utf-8")
    assert any("credential-like text: .github/workflows/ci.yml" == finding for finding in audit(root))


def test_dot_gitignore_credentials_are_scanned(tmp_path):
    root = ci_package(tmp_path)
    (root / ".gitignore").write_text("# sk-" + "testsecret1234567890123456", encoding="utf-8")
    assert any("credential-like text: .gitignore" == finding for finding in audit(root))


def test_empty_license_is_not_release_clearance(tmp_path):
    root = clean_package(tmp_path)
    (root / "LICENSE").write_text("\n", encoding="utf-8")
    assert "empty LICENSE" in audit(root)


def test_dot_gitattributes_credentials_are_scanned(tmp_path):
    root = ci_package(tmp_path)
    (root / ".gitattributes").write_text("# sk-" + "testsecret1234567890123456", encoding="utf-8")
    assert "credential-like text: .gitattributes" in audit(root)


def test_watch_page_only_is_allowlisted_with_rights_coverage(tmp_path):
    root = clean_package(tmp_path)
    (root / "docs").mkdir()
    (root / "docs/index.html").write_text("<!doctype html><title>Original demonstration</title>", encoding="utf-8")
    provenance = root / "fixtures/provenance.json"
    data = json.loads(provenance.read_text(encoding="utf-8"))
    data["asset_groups"].append({"pattern": "docs/index.html", "origin": "authored test HTML",
                               "rights": "test rights", "review_status": "approved_for_public_release"})
    provenance.write_text(json.dumps(data), encoding="utf-8")
    assert audit(root) == []
    (root / "docs/unknown.html").write_text("unknown", encoding="utf-8")
    assert "non-allowlisted file: docs/unknown.html" in audit(root)


def test_stress_provenance_rejects_unreviewed_prose_fields(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    value = json.loads((ROOT / "fixtures/stress_provenance.json").read_text(encoding="utf-8"))
    value["raw_paragraphs"] = ["Unreviewed prose must not be packaged."]
    (root / "fixtures/stress_provenance.json").write_text(json.dumps(value), encoding="utf-8")
    assert any("invalid stress provenance" in finding for finding in audit(root))


def test_missing_license_and_provenance_block_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "LICENSE").unlink()
    (root / "fixtures" / "provenance.json").unlink()
    findings = audit(root)
    assert any("LICENSE" in finding for finding in findings)
    assert any("provenance" in finding for finding in findings)


def test_private_path_credential_and_email_block_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    sensitive = "H:" + "\\" + "private" + "\n" + "sk-" + "supersecret1234567890" + "\n" + "person" + "@" + "example.com"
    (root / "README.md").write_text(sensitive, encoding="utf-8")
    findings = audit(root)
    assert any("absolute path" in finding for finding in findings)
    assert any("credential" in finding for finding in findings)
    assert any("email" in finding for finding in findings)


def test_submission_artifacts_and_unreviewed_media_block_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    for name in ["manuscript.docx", "raw_pmc.zip", "portal_receipt.json", "dke_case_level.json", "figure.png"]:
        (root / name).write_bytes(b"test")
    findings = audit(root)
    for name in ["manuscript.docx", "raw_pmc.zip", "portal_receipt.json", "dke_case_level.json", "figure.png"]:
        assert any(name in finding for finding in findings)


def test_broken_local_link_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "README.md").write_text("[missing](report/not-here.md)\n", encoding="utf-8")
    assert any("broken link" in finding for finding in audit(root))


def test_cli_nonzero_for_blocked_package(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "LICENSE").unlink()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_release.py"), str(root)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "LICENSE" in result.stdout


def test_auditor_source_does_not_trigger_its_own_path_rule(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "scripts").mkdir()
    (root / "scripts" / "audit_release.py").write_bytes((ROOT / "scripts" / "audit_release.py").read_bytes())
    findings = audit(root)
    assert any("rights coverage" in finding for finding in findings)
    assert not any("absolute path" in finding for finding in findings)


def test_invalid_or_empty_rights_metadata_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "fixtures" / "provenance.json").write_text("NOT VALID JSON", encoding="utf-8")
    (root / "RIGHTS.md").write_text("", encoding="utf-8")
    findings = audit(root)
    assert any("provenance" in finding for finding in findings)
    assert any("RIGHTS" in finding for finding in findings)


def test_unapproved_or_uncovered_asset_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    provenance_path = root / "fixtures" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["asset_groups"][1]["review_status"] = "pending_owner_review"
    provenance["asset_groups"] = [item for item in provenance["asset_groups"] if item["pattern"] != "README.md"]
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    findings = audit(root)
    assert any("approval" in finding for finding in findings)
    assert any("rights coverage" in finding for finding in findings)


def test_posix_private_paths_block_but_web_urls_do_not(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "README.md").write_text("https://example.com/public/data.json\n", encoding="utf-8")
    assert not any("absolute path" in finding for finding in audit(root))
    home_path = "/" + "home/alice/private/data.json"
    users_path = "/" + "Users/alice/private.txt"
    (root / "README.md").write_text(home_path + "\n" + users_path + "\nhttps://example.com/public/data.json\n", encoding="utf-8")
    assert any("absolute path" in finding for finding in audit(root))


def test_hash_only_article_bundle_is_allowlisted_with_explicit_rights(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    (root / "fixtures" / "article_challenge").mkdir()
    (root / "fixtures" / "article_gold").mkdir()
    for relative in ("fixtures/article_challenge/PMC5562747-good.json", "fixtures/article_gold/PMC5562747-good.json",
                     "fixtures/article_provenance.json"):
        (root / relative).write_bytes((ROOT / relative).read_bytes())
    provenance_path = root / "fixtures" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for pattern in ("fixtures/article_challenge/*.json", "fixtures/article_gold/*.json",
                    "fixtures/article_provenance.json"):
        provenance["asset_groups"].append({"pattern": pattern, "origin": "CC BY 4.0 article-derived hashes",
                                           "rights": "attributed with change notice", "review_status": "approved_for_public_release"})
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    assert audit(root) == []


def test_article_case_with_raw_prose_field_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    article_dir = root / "fixtures" / "article_challenge"
    article_dir.mkdir()
    payload = json.loads((ROOT / "fixtures" / "article_challenge" / "PMC5562747-good.json").read_text(encoding="utf-8"))
    payload["raw_text"] = "unreviewed article prose"
    (article_dir / "PMC5562747-good.json").write_text(json.dumps(payload), encoding="utf-8")
    assert any("invalid article case" in finding for finding in audit(root))


def test_article_provenance_with_raw_paragraph_field_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    source = ROOT / "fixtures" / "article_provenance.json"
    provenance = json.loads(source.read_text(encoding="utf-8"))
    provenance["articles"][0]["raw_paragraph"] = "unreviewed source text"
    (root / "fixtures" / "article_provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    assert any("article provenance fields" in finding for finding in audit(root))


def test_article_non_ccby_license_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    article_dir = root / "fixtures" / "article_challenge"
    article_dir.mkdir()
    (article_dir / "example.json").write_text("{}\n", encoding="utf-8")
    (root / "fixtures" / "article_provenance.json").write_text(json.dumps({
        "schema_version": "biosure.article-provenance/1.0",
        "articles": [{"pmcid": "PMC1234567", "license_uri": "https://creativecommons.org/licenses/by-nc/4.0/"}],
    }), encoding="utf-8")
    findings = audit(root)
    assert any("article provenance" in finding for finding in findings)


def test_article_case_without_source_provenance_blocks_release(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    article_dir = root / "fixtures" / "article_challenge"
    article_dir.mkdir()
    (article_dir / "example.json").write_text("{}\n", encoding="utf-8")
    provenance_path = root / "fixtures" / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["asset_groups"].append({"pattern": "fixtures/article_challenge/*.json",
                                       "origin": "article-derived", "rights": "test rights",
                                       "review_status": "approved_for_public_release"})
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    assert any("article provenance" in finding for finding in audit(root))


def test_article_cases_require_matching_gold_files(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    article_dir = root / "fixtures" / "article_challenge"
    article_dir.mkdir()
    (article_dir / "PMC1234567-good.json").write_text("{}\n", encoding="utf-8")
    assert any("article challenge/gold pairing" in finding for finding in audit(root))


def test_article_source_api_identifier_must_match_pmcid(tmp_path: Path) -> None:
    root = clean_package(tmp_path)
    source = ROOT / "fixtures" / "article_provenance.json"
    article_provenance = json.loads(source.read_text(encoding="utf-8"))
    article_provenance["articles"][0]["source_api_url"] = article_provenance["articles"][0]["source_api_url"].replace("5562747", "9999999")
    (root / "fixtures" / "article_provenance.json").write_text(json.dumps(article_provenance), encoding="utf-8")
    assert any("article provenance API URL" in finding for finding in audit(root))
