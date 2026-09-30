"""Build hash-only article-derived cases from official PMC OAI-PMH JATS.

This optional generation step needs network access. Evaluation of the checked-in
JSON remains offline. No fetched XML or paragraph prose is written to disk.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ARTICLE_IDS = ("PMC5562747", "PMC7170869", "PMC6745596")
LICENSE_URI = "https://creativecommons.org/licenses/by/4.0/"
MAX_XML_BYTES = 4_000_000


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _descendants(node: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in node.iter() if _local_name(element.tag) == name]


def _text(node: ET.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _article_id(meta: ET.Element, id_type: str) -> str:
    for element in _descendants(meta, "article-id"):
        if element.get("pub-id-type") == id_type:
            return _text(element)
    raise ValueError(f"missing article {id_type}")


def extract_article(xml_bytes: bytes, pmcid: str) -> dict:
    """Return only source metadata and three body-paragraph hashes."""
    if len(xml_bytes) > MAX_XML_BYTES:
        raise ValueError("JATS record exceeds size limit")
    root = ET.fromstring(xml_bytes)
    articles = _descendants(root, "article")
    if len(articles) != 1:
        raise ValueError("expected exactly one JATS article")
    article = articles[0]
    fronts = [child for child in article if _local_name(child.tag) == "front"]
    bodies = [child for child in article if _local_name(child.tag) == "body"]
    if len(fronts) != 1 or len(bodies) != 1:
        raise ValueError("missing unique JATS front or body")
    metas = _descendants(fronts[0], "article-meta")
    if len(metas) != 1:
        raise ValueError("missing unique article metadata")
    meta = metas[0]
    if _article_id(meta, "pmcid") != pmcid:
        raise ValueError("PMCID mismatch")
    license_refs = [_text(node).replace("http://", "https://", 1).rstrip("/") + "/"
                    for node in _descendants(meta, "license_ref")]
    if LICENSE_URI not in license_refs:
        raise ValueError("article license is not explicit CC BY 4.0")
    titles = _descendants(meta, "article-title")
    if len(titles) != 1:
        raise ValueError("missing unique article title")
    paragraphs = []
    for index, node in enumerate(_descendants(bodies[0], "p"), start=1):
        content = _text(node)
        if not content:
            continue
        paragraphs.append({
            "source_locator": f"body//p[{index}]",
            "text_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
        if len(paragraphs) == 3:
            break
    if len(paragraphs) != 3:
        raise ValueError("fewer than three nonempty body paragraphs")
    return {
        "pmcid": pmcid,
        "doi": _article_id(meta, "doi"),
        "title": _text(titles[0]),
        "license_uri": LICENSE_URI,
        "article_xml_sha256": hashlib.sha256(ET.tostring(article, encoding="utf-8")).hexdigest(),
        "paragraphs": paragraphs,
    }


def _block(block_id: str, text_hash: str) -> dict:
    return {"block_id": block_id, "kind": "paragraph", "text_sha256": text_hash,
            "section_level": 0, "target_id": None}


def article_cases(article: dict) -> dict[str, tuple[dict, dict]]:
    pmcid = article["pmcid"]
    blocks = [_block(f"p{index}", entry["text_sha256"])
              for index, entry in enumerate(article["paragraphs"], start=1)]
    gold = {"record_id": f"article-{pmcid}", "blocks": blocks, "citation_anchors": []}
    damaged = copy.deepcopy(gold)
    damaged["blocks"].pop(1)
    insertion = {
        "block_id": "p2", "text_sha256": blocks[1]["text_sha256"],
        "before_id": "p1", "after_id": "p3",
        "source_id": f"{pmcid}:OAI-PMH:{article['paragraphs'][1]['source_locator']}",
    }
    base = {
        "case_id": "", "damaged": damaged,
        "candidates": [{"candidate_id": "candidate-1", "operation": "INSERT_PARAGRAPH",
                        "document": copy.deepcopy(gold)}],
        "evidence": {"trusted_insertions": [insertion], "trusted_identities": []},
    }
    cases = {}
    for suffix in ("good", "wrong-hash", "no-evidence"):
        request = copy.deepcopy(base)
        name = f"{pmcid}-{suffix}"
        request["case_id"] = name
        if suffix == "wrong-hash":
            request["candidates"][0]["document"]["blocks"][1]["text_sha256"] = hashlib.sha256(
                (blocks[1]["text_sha256"] + "|synthetic-mutant").encode("ascii")
            ).hexdigest()
        elif suffix == "no-evidence":
            request["evidence"]["trusted_insertions"] = []
        cases[name] = (request, copy.deepcopy(gold))
    return cases


def fetch_article(pmcid: str) -> tuple[dict, str]:
    if not re.fullmatch(r"PMC[0-9]+", pmcid):
        raise ValueError("invalid PMCID")
    url = ("https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord"
           f"&identifier=oai:pubmedcentral.nih.gov:{pmcid[3:]}&metadataPrefix=pmc")
    request = urllib.request.Request(url, headers={"User-Agent": "BioSURE-article-challenge/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        xml_bytes = response.read(MAX_XML_BYTES + 1)
    return extract_article(xml_bytes, pmcid), url


def emit(root: Path) -> None:
    collected = []
    for pmcid in ARTICLE_IDS:
        item, url = fetch_article(pmcid)
        item["source_api_url"] = url
        item["article_url"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        collected.append(item)
        time.sleep(0.4)  # PMC OAI-PMH limit is at most three requests per second.
    challenge_dir = root / "article_challenge"
    gold_dir = root / "article_gold"
    challenge_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    for article in collected:
        for name, (request, gold) in article_cases(article).items():
            (challenge_dir / f"{name}.json").write_bytes((json.dumps(request, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            (gold_dir / f"{name}.json").write_bytes((json.dumps(gold, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    provenance = {
        "schema_version": "biosure.article-provenance/1.0",
        "generator": "scripts/build_article_challenge.py",
        "paragraph_normalization": "join XML itertext, collapse whitespace to single ASCII spaces, UTF-8 SHA-256",
        "selection": "first three nonempty body descendant p elements in document order",
        "case_design": "one correct insertion, one synthetic wrong-hash candidate, one missing-evidence abstention per article",
        "limitations": "article-derived structure with constructed defects; not native errors, independent adjudication, or biological validation",
        "articles": collected,
    }
    (root / "article_provenance.json").write_bytes((json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    emit(args.output_dir)
