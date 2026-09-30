"""Fail-closed file and text audit for a staged BioSURE public package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from biosure.schema import parse_document, parse_request


REQUIRED = ("README.md", "RIGHTS.md", "LICENSE", "fixtures/provenance.json")
TEXT_SUFFIXES = {".py", ".md", ".toml", ".json", ".html", ".css", ".js", ".txt", ".yml"}
PROHIBITED_NAME = re.compile(r"(manuscript|portal.?receipt|submission.?receipt|raw.?pmc|case.?level|reviewer|cover.?letter)", re.IGNORECASE)
_SLASH = chr(92)
_DRIVE_PATTERN = r"\b[A-Za-z]:[" + re.escape(_SLASH) + "/]"
_UNC_PATTERN = re.escape(_SLASH * 2) + "[^" + re.escape(_SLASH) + r"\s]+" + re.escape(_SLASH) + "[^" + re.escape(_SLASH) + r"\s]+"
WINDOWS_PATH = re.compile(_DRIVE_PATTERN + "|" + _UNC_PATTERN)
POSIX_PRIVATE_PATH = re.compile(r"(?<![A-Za-z0-9_:/])/(?:home|Users|tmp|var|mnt|private)/[^\s<>)\]]+")
CREDENTIAL = re.compile(r"\b(?:sk-[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{12,}|AIza[A-Za-z0-9_-]{12,})\b")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HEX64 = re.compile(r"[0-9a-f]{64}")


def _allowed(relative: str) -> bool:
    parts = Path(relative).parts
    if relative in {"README.md", "RIGHTS.md", "LICENSE", "pyproject.toml", ".gitignore", ".gitattributes", ".github/workflows/ci.yml", "docs/index.html", "tests/test_browser_logic.js"}:
        return True
    if len(parts) == 2 and parts[0] in {"biosure", "scripts", "tests"} and parts[1].endswith(".py"):
        return True
    if len(parts) == 3 and parts[:2] == ("biosure", "static") and Path(parts[2]).suffix in {".html", ".css", ".js"}:
        return True
    if len(parts) == 3 and parts[:2] in {("fixtures", "challenge"), ("fixtures", "gold"),
                                        ("fixtures", "article_challenge"), ("fixtures", "article_gold"),
                                        ("fixtures", "stress_challenge"), ("fixtures", "stress_gold")} and parts[2].endswith(".json"):
        return True
    if len(parts) == 2 and parts[0] in {"fixtures", "results"} and parts[1].endswith(".json"):
        return True
    if len(parts) == 2 and parts[0] in {"report", "video"} and parts[1].endswith(".md"):
        return True
    return False


def _rights_metadata(root: Path, files: list[str]) -> list[str]:
    findings: list[str] = []
    license_file = root / "LICENSE"
    if license_file.is_file():
        try:
            if not license_file.read_text(encoding="utf-8").strip():
                findings.append("empty LICENSE")
        except UnicodeError:
            findings.append("non-UTF-8 LICENSE")
    rights_file = root / "RIGHTS.md"
    if rights_file.is_file():
        try:
            if not rights_file.read_text(encoding="utf-8").strip():
                findings.append("empty RIGHTS.md")
        except UnicodeError:
            findings.append("non-UTF-8 RIGHTS.md")
    provenance_file = root / "fixtures" / "provenance.json"
    if not provenance_file.is_file():
        return findings
    try:
        data = json.loads(provenance_file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return findings + ["invalid provenance JSON"]
    if not isinstance(data, dict) or data.get("schema_version") != "biosure.synthetic-provenance/1.0":
        return findings + ["invalid provenance schema"]
    if any(not isinstance(data.get(key), str) or not data[key].strip() for key in ("author", "rights")):
        findings.append("missing provenance rights or author")
    groups = data.get("asset_groups")
    if not isinstance(groups, list) or not groups:
        return findings + ["missing provenance asset rights coverage"]
    patterns: list[str] = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict) or any(not isinstance(group.get(key), str) or not group[key].strip()
                                               for key in ("pattern", "origin", "rights", "review_status")):
            findings.append(f"invalid provenance asset group {index}")
            continue
        patterns.append(group["pattern"])
        if group["review_status"] != "approved_for_public_release":
            findings.append(f"missing rights approval: {group['pattern']}")
    for relative in files:
        if not any(fnmatchcase(relative, pattern) for pattern in patterns):
            findings.append(f"missing rights coverage: {relative}")
    return findings


def _article_metadata(root: Path, files: list[str]) -> list[str]:
    article_path = root / "fixtures" / "article_provenance.json"
    challenge_names = {Path(name).name for name in files if name.startswith("fixtures/article_challenge/")}
    gold_names = {Path(name).name for name in files if name.startswith("fixtures/article_gold/")}
    has_article_cases = bool(challenge_names or gold_names)
    if not has_article_cases and not article_path.is_file():
        return []
    findings = []
    if challenge_names != gold_names:
        findings.append("article challenge/gold pairing mismatch")
    for name in files:
        try:
            if name.startswith("fixtures/article_challenge/"):
                parse_request(json.loads((root / name).read_text(encoding="utf-8")))
            elif name.startswith("fixtures/article_gold/"):
                parse_document(json.loads((root / name).read_text(encoding="utf-8")))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            findings.append(f"invalid article case: {name}")
    if not article_path.is_file():
        return findings + ["missing article provenance"]
    try:
        data = json.loads(article_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return findings + ["invalid article provenance JSON"]
    if not isinstance(data, dict) or data.get("schema_version") != "biosure.article-provenance/1.0":
        return findings + ["invalid article provenance schema"]
    if set(data) != {"schema_version", "generator", "paragraph_normalization", "selection",
                     "case_design", "limitations", "articles"}:
        return findings + ["invalid article provenance fields"]
    articles = data.get("articles")
    if not isinstance(articles, list) or not articles:
        return findings + ["invalid article provenance articles"]
    seen: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            return findings + ["invalid article provenance entry"]
        if set(article) != {"pmcid", "doi", "title", "license_uri", "article_xml_sha256",
                            "paragraphs", "source_api_url", "article_url"}:
            return findings + ["invalid article provenance fields"]
        pmcid = article.get("pmcid")
        if not isinstance(pmcid, str) or not re.fullmatch(r"PMC[0-9]+", pmcid) or pmcid in seen:
            return findings + ["invalid article provenance PMCID"]
        seen.add(pmcid)
        if article.get("license_uri") != "https://creativecommons.org/licenses/by/4.0/":
            return findings + ["invalid article provenance license"]
        if article.get("article_url") != f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/":
            return findings + ["invalid article provenance source URL"]
        api_url = ("https://pmc.ncbi.nlm.nih.gov/api/oai/v1/mh/?verb=GetRecord"
                   f"&identifier=oai:pubmedcentral.nih.gov:{pmcid[3:]}&metadataPrefix=pmc")
        if article.get("source_api_url") != api_url:
            return findings + ["invalid article provenance API URL"]
        digest = article.get("article_xml_sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            return findings + ["invalid article provenance XML digest"]
        paragraphs = article.get("paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) != 3:
            return findings + ["invalid article provenance paragraph selection"]
        for paragraph in paragraphs:
            if not isinstance(paragraph, dict) or set(paragraph) != {"source_locator", "text_sha256"} or not isinstance(paragraph.get("source_locator"), str) or not isinstance(paragraph.get("text_sha256"), str) or not HEX64.fullmatch(paragraph["text_sha256"]):
                return findings + ["invalid article provenance paragraph hash"]
    for name in challenge_names:
        if not any(name.startswith(pmcid + "-") for pmcid in seen):
            findings.append(f"article challenge has no matching source provenance: {name}")
    return findings


def audit(root: Path) -> list[str]:
    root = root.resolve()
    findings: list[str] = []
    for required in REQUIRED:
        if not (root / required).is_file():
            findings.append(f"missing required file: {required}")
    if not root.is_dir():
        return findings + ["package root does not exist"]
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append(f"symlink not allowed: {relative}")
            continue
        if path.is_dir():
            continue
        files.append(relative)
        if PROHIBITED_NAME.search(path.name):
            findings.append(f"prohibited artifact: {relative}")
        if not _allowed(relative):
            findings.append(f"non-allowlisted file: {relative}")
        if path.suffix not in TEXT_SUFFIXES and path.name not in {"LICENSE", ".gitignore", ".gitattributes"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            findings.append(f"non-UTF-8 text: {relative}")
            continue
        if WINDOWS_PATH.search(content) or POSIX_PRIVATE_PATH.search(content):
            findings.append(f"private absolute path: {relative}")
        if CREDENTIAL.search(content):
            findings.append(f"credential-like text: {relative}")
        if EMAIL.search(content):
            findings.append(f"email address: {relative}")
        if path.suffix == ".md":
            for target in MARKDOWN_LINK.findall(content):
                target = target.split("#", 1)[0].strip()
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                if not (path.parent / target).is_file():
                    findings.append(f"broken link in {relative}: {target}")
    findings.extend(_rights_metadata(root, files))
    findings.extend(_article_metadata(root, files))
    stress_cases = {Path(name).name for name in files if name.startswith("fixtures/stress_challenge/")}
    stress_gold = {Path(name).name for name in files if name.startswith("fixtures/stress_gold/")}
    if stress_cases != stress_gold:
        findings.append("stress challenge/gold pairing mismatch")
    stress_manifest = root / "fixtures/stress_provenance.json"
    if stress_cases and not stress_manifest.is_file():
        findings.append("missing stress provenance")
    if stress_manifest.is_file():
        try:
            data = json.loads(stress_manifest.read_text(encoding="utf-8"))
            keys = {"schema_version", "seed", "generator", "source_graphs", "cases", "paragraph_counts",
                    "conditions", "origin", "limitations"}
            if (not isinstance(data, dict) or set(data) != keys
                    or data["schema_version"] != "biosure.stress-provenance/1.0"
                    or type(data["cases"]) is not int or type(data["source_graphs"]) is not int
                    or data["cases"] != 168 or data["source_graphs"] != 12
                    or data["paragraph_counts"] != [16, 32, 64]
                    or not isinstance(data["conditions"], list) or len(data["conditions"]) != 14
                    or any(not isinstance(item, str) for item in data["conditions"])
                    or len(set(data["conditions"])) != 14
                    or data["generator"] != "scripts/build_stress_challenge.py"
                    or (stress_cases and len(stress_cases) != data["cases"])):
                findings.append("invalid stress provenance schema or pairing count")
        except (OSError, UnicodeError, ValueError):
            findings.append("invalid stress provenance JSON")
    for name in files:
        try:
            if name.startswith("fixtures/stress_challenge/"):
                parse_request(json.loads((root / name).read_text(encoding="utf-8")))
            elif name.startswith("fixtures/stress_gold/"):
                parse_document(json.loads((root / name).read_text(encoding="utf-8")))
        except (OSError, UnicodeError, ValueError):
            findings.append(f"invalid stress case: {name}")
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a staged BioSURE release directory")
    parser.add_argument("package_root", type=Path)
    args = parser.parse_args()
    findings = audit(args.package_root)
    if findings:
        for finding in findings:
            print("BLOCK: " + finding)
        return 1
    print("PASS: staged package file and text audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
