from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from biosure.evaluate import decide_case, score_case, summarize


def generator():
    try:
        return importlib.import_module("scripts.build_article_challenge")
    except ModuleNotFoundError:
        pytest.fail("article challenge generator is missing")


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample_xml(license_uri: str = "https://creativecommons.org/licenses/by/4.0/") -> bytes:
    return f'''<OAI-PMH><GetRecord><record><metadata><article>
      <front><article-meta>
        <article-id pub-id-type="pmcid">PMC1234567</article-id>
        <article-id pub-id-type="doi">10.1234/example</article-id>
        <title-group><article-title>Example chip study</article-title></title-group>
        <permissions><license><license_ref>{license_uri}</license_ref></license></permissions>
      </article-meta></front>
      <body><sec><title>Methods</title>
        <p id="p-a">Alpha  beta.</p><p id="p-b">Gamma <italic>delta</italic>.</p>
        <p id="p-c">Epsilon zeta.</p>
      </sec></body>
    </article></metadata></record></GetRecord></OAI-PMH>'''.encode("utf-8")


def test_extract_article_hashes_body_paragraphs_without_copying_prose() -> None:
    item = generator().extract_article(sample_xml(), "PMC1234567")
    assert item["pmcid"] == "PMC1234567"
    assert item["doi"] == "10.1234/example"
    assert item["title"] == "Example chip study"
    assert [p["text_sha256"] for p in item["paragraphs"]] == [h("Alpha beta."), h("Gamma delta."), h("Epsilon zeta.")]
    assert "Alpha beta" not in json.dumps(item)
    assert "Gamma delta" not in json.dumps(item)


def test_extract_article_rejects_wrong_identity_or_license() -> None:
    with pytest.raises(ValueError, match="PMCID"):
        generator().extract_article(sample_xml(), "PMC9999999")
    with pytest.raises(ValueError, match="license"):
        generator().extract_article(sample_xml("https://creativecommons.org/licenses/by-nc/4.0/"), "PMC1234567")


def test_article_cases_keep_gold_out_of_requests() -> None:
    cases = generator().article_cases(generator().extract_article(sample_xml(), "PMC1234567"))
    assert len(cases) == 3
    good = cases["PMC1234567-good"]
    bad_hash = cases["PMC1234567-wrong-hash"]
    no_evidence = cases["PMC1234567-no-evidence"]
    assert good[0]["damaged"]["record_id"] == "article-PMC1234567"
    assert good[0]["candidates"][0]["document"] == good[1]
    assert bad_hash[0]["candidates"][0]["document"] != bad_hash[1]
    assert no_evidence[0]["evidence"]["trusted_insertions"] == []
    for request, gold in cases.values():
        assert "gold" not in request
        assert len(gold["blocks"]) == 3


def test_checked_in_article_cases_score_separately() -> None:
    root = ROOT / "fixtures"
    paths = sorted((root / "article_challenge").glob("*.json"))
    assert len(paths) == 9
    results = [score_case(decide_case(path), root / "article_gold" / path.name) for path in paths]
    summary = summarize(results)
    assert summary["source_graphs"] == 3
    assert summary["cases"] == 9
    assert summary["exact_auto"] == 3
    assert summary["incorrect_auto"] == 0
    assert summary["abstentions"] == 6
    assert summary["wrong_executable_candidates_total"] == 3
    provenance = json.loads((root / "article_provenance.json").read_text(encoding="utf-8"))
    assert len(provenance["articles"]) == 3
    for article in provenance["articles"]:
        assert article["license_uri"] == "https://creativecommons.org/licenses/by/4.0/"
        assert article["pmcid"] in {"PMC5562747", "PMC7170869", "PMC6745596"}


def test_article_emission_uses_portable_lf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = generator()
    article = module.extract_article(sample_xml(), "PMC1234567")
    monkeypatch.setattr(module, "ARTICLE_IDS", ("PMC1234567",))
    monkeypatch.setattr(module, "fetch_article", lambda pmcid: (article, "https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/"))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    module.emit(tmp_path)
    paths = sorted(tmp_path.rglob("*.json"))
    assert len(paths) == 7
    for path in paths:
        data = path.read_bytes()
        assert b"\r\n" not in data
        assert data.endswith(b"\n")
