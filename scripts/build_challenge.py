"""Deterministically regenerate the small, project-authored public challenge."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path


SEED = "biosure-synthetic-20260930-v2"


def block(block_id: str, text: str) -> dict:
    return {
        "block_id": block_id,
        "kind": "paragraph",
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "section_level": 0,
        "target_id": None,
    }


def insertion() -> tuple[dict, dict]:
    damaged = {"record_id": "synthetic-source-insertion", "blocks": [block("p1", "alpha"), block("p3", "gamma")], "citation_anchors": []}
    gold = copy.deepcopy(damaged)
    gold["blocks"].insert(1, block("p2", "beta"))
    request = {
        "case_id": "",
        "damaged": damaged,
        "candidates": [{"candidate_id": "candidate-1", "operation": "INSERT_PARAGRAPH", "document": copy.deepcopy(gold)}],
        "evidence": {
            "trusted_insertions": [
                {
                    "block_id": "p2",
                    "text_sha256": block("p2", "beta")["text_sha256"],
                    "before_id": "p1",
                    "after_id": "p3",
                    "source_id": "project-authored-registry-insertion",
                }
            ],
            "trusted_identities": [],
        },
    }
    return request, gold


def duplicate() -> tuple[dict, dict]:
    damaged = {
        "record_id": "synthetic-source-duplicate",
        "blocks": [block("p1", "alpha"), block("p1copy", "alpha"), block("p2", "beta")],
        "citation_anchors": [],
    }
    gold = copy.deepcopy(damaged)
    gold["blocks"].pop(1)
    request = {
        "case_id": "",
        "damaged": damaged,
        "candidates": [{"candidate_id": "candidate-1", "operation": "REMOVE_DUPLICATE", "document": copy.deepcopy(gold)}],
        "evidence": {
            "trusted_insertions": [],
            "trusted_identities": [
                {
                    "retained_block_id": "p1",
                    "duplicate_block_id": "p1copy",
                    "text_sha256": block("p1", "alpha")["text_sha256"],
                    "source_id": "project-authored-registry-duplicate",
                }
            ],
        },
    }
    return request, gold


def challenge_cases() -> dict[str, tuple[dict, dict]]:
    good, insertion_gold = insertion()
    cases: dict[str, tuple[dict, dict]] = {}

    def add(name: str, request: dict, gold: dict) -> None:
        request["case_id"] = name
        cases[name] = (request, copy.deepcopy(gold))

    add("01-insertion-good", copy.deepcopy(good), insertion_gold)
    wrong_hash = copy.deepcopy(good)
    wrong_hash["candidates"][0]["document"]["blocks"][1]["text_sha256"] = block("p2", "substituted")["text_sha256"]
    add("02-insertion-wrong-hash", wrong_hash, insertion_gold)
    wrong_location = copy.deepcopy(good)
    inserted = wrong_location["candidates"][0]["document"]["blocks"].pop(1)
    wrong_location["candidates"][0]["document"]["blocks"].insert(0, inserted)
    add("03-insertion-wrong-location", wrong_location, insertion_gold)
    wrong_id = copy.deepcopy(good)
    wrong_id["candidates"][0]["document"]["blocks"][1]["block_id"] = "p9"
    add("04-insertion-wrong-id", wrong_id, insertion_gold)
    missing_evidence = copy.deepcopy(good)
    missing_evidence["evidence"]["trusted_insertions"] = []
    add("05-insertion-no-evidence", missing_evidence, insertion_gold)
    ambiguous = copy.deepcopy(good)
    second = copy.deepcopy(ambiguous["candidates"][0])
    second["candidate_id"] = "candidate-2"
    second["document"]["blocks"][1] = block("p4", "alternative")
    ambiguous["candidates"].append(second)
    ambiguous["evidence"]["trusted_insertions"].append(
        {
            "block_id": "p4",
            "text_sha256": block("p4", "alternative")["text_sha256"],
            "before_id": "p1",
            "after_id": "p3",
            "source_id": "project-authored-registry-alternative",
        }
    )
    add("06-insertion-ambiguous", ambiguous, insertion_gold)

    duplicate_good, duplicate_gold = duplicate()
    add("07-duplicate-good", copy.deepcopy(duplicate_good), duplicate_gold)
    wrong_removal = copy.deepcopy(duplicate_good)
    wrong_removal["candidates"][0]["document"]["blocks"][0] = block("p1copy", "alpha")
    add("08-duplicate-remove-retained", wrong_removal, duplicate_gold)
    return cases


def emit(root: Path) -> None:
    (root / "challenge").mkdir(parents=True, exist_ok=True)
    (root / "gold").mkdir(parents=True, exist_ok=True)
    for name, (request, gold) in challenge_cases().items():
        (root / "challenge" / f"{name}.json").write_bytes((json.dumps(request, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        (root / "gold" / f"{name}.json").write_bytes((json.dumps(gold, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    provenance = {
        "schema_version": "biosure.synthetic-provenance/1.0",
        "seed": SEED,
        "author": "HyunStudio / BioSURE project",
        "rights": "MIT project-authored assets in the audited no-prior export; separately attributed CC BY 4.0 article derivatives",
        "owner_authorization": "2026-09-30: project owner explicitly authorized agent-managed decisions and approval for submission preparation except registration. Applies only to the audited no-prior export, not private manuscript/source history or independent scientific validation.",
        "source_graphs": 2,
        "derived_cases": 8,
        "limitations": "constructed examples, not independent articles or native errors",
        "asset_groups": [
            {
                "pattern": pattern,
                "origin": ("project-authored fictional paragraph inputs; no experimental observations or article quotations"
                           if pattern == "fixtures/workflow_examples.json" else
                           "CC BY 4.0 PMC JATS article-derived hashes; see fixtures/article_provenance.json and RIGHTS.md"
                           if pattern.startswith("fixtures/article_") else
                           "24 explicitly CC BY 4.0 PMC JATS articles; full per-record authors, title, DOI, URL, license and excerpt/change notice in corpus and RIGHTS.md"
                           if pattern == "fixtures/ml_corpus.json" else
                           "Short modified text-layer excerpts from Tward et al., DOI 10.1038/s41467-025-65317-7, PMCID PMC12645051; CC BY 4.0 attribution and change notice in report/public-rights.md"
                           if pattern == "fixtures/native_pilot_inputs.json" else
                           "Single-agent visually checked short transcription of Tward et al., DOI 10.1038/s41467-025-65317-7; CC BY 4.0 attribution and change notice in report/public-rights.md"
                           if pattern == "fixtures/native_pilot_gold.json" else
                           "Short modified first-page title/abstract text-layer excerpts from Skardal et al. DOI 10.1038/s41598-017-08879-x; Rogal et al. DOI 10.1038/s41598-020-63710-4; Wang et al. DOI 10.1038/s41378-025-00933-3; Kanioura et al. DOI 10.3390/mi16070740; Liu et al. DOI 10.3389/fonc.2025.1602225. CC BY 4.0 attribution and change notice in report/public-rights.md"
                           if pattern == "fixtures/ooc_pdf_*_inputs.json" else
                           "Single-agent JATS/rendered-PDF title/abstract adjudication of the five credited OoC articles; the Frontiers abstract is unscorable and excluded. See report/public-rights.md"
                           if pattern == "fixtures/ooc_pdf_*_gold.json" else
                           "Eight separately credited CC BY 4.0 organ-on-a-chip/microphysiological-system PMC Cloud PDF/XML deposits; per-file authors, DOI, source URL, hashes and modification notice are embedded in each input fixture and credited in RIGHTS.md"
                           if pattern == "fixtures/prospective_ooc_PMC*_inputs.json" else
                           "Continuous JATS title/abstract excerpts from the same eight credited CC BY 4.0 articles; developer-agent boundary check, not independent expert gold"
                           if pattern == "fixtures/prospective_ooc_PMC*_gold.json" else
                           "Project-authored prelocked source/split/unit manifest of eight attributed CC BY 4.0 articles"
                           if pattern == "fixtures/prospective_ooc_manifest.json" else
                           "Decision records include attributed CC BY 4.0 article-derived title/abstract excerpts from the eight credited prospective-audit sources"
                           if pattern == "results/prospective_ooc_decisions.json" else
                           "Two separately credited CC BY 4.0 PMC Cloud deposits selected by metadata-only follow-up lock; author, DOI, URLs, hashes and modification notice are in each input fixture and RIGHTS.md"
                           if pattern == "fixtures/followup_ooc_PMC*_inputs.json" else
                           "Same-article continuous JATS title/abstract excerpts from the two credited follow-up sources; one-agent page-boundary check is not independent truth"
                           if pattern == "fixtures/followup_ooc_PMC*_gold.json" else
                           "Project-authored prelocked metadata manifest for two attributed CC BY 4.0 articles"
                           if pattern == "fixtures/followup_ooc_manifest.json" else
                           "Decision records include modified PDF-text/JATS title/abstract excerpts from the two credited follow-up articles"
                           if pattern == "results/followup_ooc_decisions.json" else
                           "project-generated learned weights from attributed CC BY 4.0 PMC excerpt pairs; see fixtures/ml_corpus.json and RIGHTS.md"
                           if pattern == "fixtures/ml_model.json" else
                           "project-generated per-source metrics from eight attributed CC BY 4.0 title/abstract inputs; see report/public-rights.md"
                           if pattern == "results/learned_upstream_audit.json" else
                           "Static judge replay with attributed CC BY 4.0 modified page-one title excerpts from Kim et al., DOI 10.1002/adhm.202502711, plus project-authored fictional controls; see RIGHTS.md"
                           if pattern == "docs/judge/data.json" else
                           "project-generated results; article-derived excerpts in decision files retain the separately documented CC BY 4.0 rights in RIGHTS.md"
                           if pattern == "results/*.json" else
                           "project-authored synthetic or project-owned source; see RIGHTS.md"),
                "rights": ("CC BY 4.0 hash-only derivatives; verified article attribution and change notice retained; owner-authorized no-prior export"
                           if pattern.startswith("fixtures/article_") else
                           "CC BY 4.0 attributed paragraph excerpts and constructed-variant source material; no source XML, PDF, images or patient data packaged"
                           if pattern == "fixtures/ml_corpus.json" else
                           "CC BY 4.0 attributed short excerpts; no publisher PDF, figures or full article packaged"
                           if pattern == "fixtures/native_pilot_inputs.json" else
                           "CC BY 4.0 attributed short excerpts; not independent expert adjudication"
                           if pattern == "fixtures/native_pilot_gold.json" else
                           "CC BY 4.0 attributed short excerpts; no publisher PDF, figures or full article packaged"
                           if pattern == "fixtures/ooc_pdf_*_inputs.json" else
                           "CC BY 4.0 attributed short excerpts; not independent expert adjudication"
                           if pattern == "fixtures/ooc_pdf_*_gold.json" else
                           "CC BY 4.0 attributed title/abstract excerpts; no source PDF, XML, figure or page image packaged"
                           if pattern == "fixtures/prospective_ooc_PMC*_inputs.json" else
                           "CC BY 4.0 attributed modified short excerpts; same-article canonical reference, not independent source truth"
                           if pattern == "fixtures/prospective_ooc_PMC*_gold.json" else
                           "MIT project-authored metadata, distributed alongside attributed CC BY 4.0 source excerpts"
                           if pattern == "fixtures/prospective_ooc_manifest.json" else
                           "CC BY 4.0 attributed modified excerpts; no PDF/XML/figures packaged"
                           if pattern == "results/prospective_ooc_decisions.json" else
                           "CC BY 4.0 attributed modified title/abstract excerpts; no PDF/XML/figure/page image packaged"
                           if pattern == "fixtures/followup_ooc_PMC*_inputs.json" else
                           "CC BY 4.0 attributed modified short excerpts; not independent expert adjudication"
                           if pattern == "fixtures/followup_ooc_PMC*_gold.json" else
                           "MIT project-authored metadata distributed with separately attributed CC BY 4.0 excerpts"
                           if pattern == "fixtures/followup_ooc_manifest.json" else
                           "CC BY 4.0 attributed modified excerpts; no source PDF/XML/figures packaged"
                           if pattern == "results/followup_ooc_decisions.json" else
                           "MIT project-generated model artifact, distributed with CC BY 4.0 training-source attribution and change notice"
                           if pattern == "fixtures/ml_model.json" else
                           "MIT project-generated measurements distributed with the eight sources' CC BY 4.0 attribution and change notices"
                           if pattern == "results/learned_upstream_audit.json" else
                           "CC BY 4.0 attributed short modified excerpt for the public sample; original project-generated decisions and fictional controls under MIT, no full PDF/XML/figures"
                           if pattern == "docs/judge/data.json" else
                           "MIT applies to original project-generated portions only; any embedded article-derived text retains attributed CC BY 4.0 status"
                           if pattern == "results/*.json" else
                           "MIT project-authored material; owner-authorized audited no-prior export only, excluded prior/manuscript copies not licensed"),
                "review_status": "approved_for_public_release",
            }
            for pattern in (
                "tests/test_browser_logic.js", "tests/test_judge_mode.js", "fixtures/workflow_examples.json",
                "fixtures/stress_challenge/*.json", "fixtures/stress_gold/*.json", "fixtures/stress_provenance.json",
                "README.md", "RIGHTS.md", "LICENSE", "pyproject.toml", ".gitignore", ".gitattributes", ".github/workflows/ci.yml", "docs/index.html",
                "docs/judge/*.html", "docs/judge/*.css", "docs/judge/*.js", "docs/judge/data.json",
                "biosure/*.py", "biosure/static/*.html", "biosure/static/*.css", "biosure/static/*.js",
                "scripts/*.py", "tests/*.py", "fixtures/provenance.json",
                "fixtures/challenge/*.json", "fixtures/gold/*.json", "results/*.json",
                "fixtures/article_challenge/*.json", "fixtures/article_gold/*.json", "fixtures/article_provenance.json",
                "fixtures/ml_corpus.json", "fixtures/native_pilot_inputs.json", "fixtures/native_pilot_gold.json",
                "fixtures/ooc_pdf_*_inputs.json", "fixtures/ooc_pdf_*_gold.json",
                "fixtures/prospective_ooc_PMC*_inputs.json", "fixtures/prospective_ooc_PMC*_gold.json",
                "fixtures/prospective_ooc_manifest.json", "results/prospective_ooc_decisions.json",
                "fixtures/followup_ooc_PMC*_inputs.json", "fixtures/followup_ooc_PMC*_gold.json",
                "fixtures/followup_ooc_manifest.json", "results/followup_ooc_decisions.json",
                "fixtures/ml_model.json", "results/learned_upstream_audit.json",
                "report/*.md", "video/*.md",
            )
        ],
    }
    (root / "provenance.json").write_bytes((json.dumps(provenance, sort_keys=True, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_challenge.py OUTPUT_DIR")
    emit(Path(sys.argv[1]))
