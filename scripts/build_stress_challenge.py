"""Deterministic exploratory counterexamples, not sampled OoC experiments."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


CONDITIONS = ("insert-good", "remove-good", "no-change", "missing-evidence", "wrong-hash",
              "wrong-location", "wrong-id", "extra-metadata", "unrelated-edit", "conflicting-evidence",
              "supported-ambiguity", "forged-evidence", "wrong-retained", "reordered")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SOURCE_COUNT = 12


def source_document(source: int) -> dict:
    """The authored, undamaged source graph for one stress source (1-based)."""
    size = (16, 32, 64)[(source - 1) // 4]
    blocks = [{"block_id": f"p{i + 1}", "kind": "paragraph", "section_level": 0,
               "target_id": None, "text_sha256": digest(f"fictitious-ooc-conversion-source-{source}:paragraph-{i}")}
              for i in range(size)]
    return {"record_id": f"stress-source-{source:02d}", "blocks": blocks, "citation_anchors": []}


def build_cases() -> dict[str, tuple[dict, dict]]:
    cases = {}
    for source in range(1, SOURCE_COUNT + 1):
        gold = source_document(source)
        blocks = gold["blocks"]
        size = len(blocks)
        middle = size // 2
        missing = blocks[middle]
        damaged = copy.deepcopy(gold)
        damaged["blocks"].pop(middle)
        entry = {"block_id": missing["block_id"], "text_sha256": missing["text_sha256"],
                 "before_id": blocks[middle - 1]["block_id"], "after_id": blocks[middle + 1]["block_id"],
                 "source_id": f"project-authored-stress-registry-{source}"}
        base = {"case_id": "", "damaged": damaged,
                "candidates": [{"candidate_id": "candidate-1", "operation": "INSERT_PARAGRAPH", "document": copy.deepcopy(gold)}],
                "evidence": {"trusted_insertions": [entry], "trusted_identities": []}}
        for condition in CONDITIONS:
            request = copy.deepcopy(base)
            name = f"s{source:02d}--{condition}"
            request["case_id"] = name
            candidate = request["candidates"][0]["document"]
            evidence = request["evidence"]
            if condition in {"remove-good", "wrong-retained"}:
                duplicate = {**missing, "block_id": "extra-duplicate"}
                request["damaged"] = copy.deepcopy(gold)
                request["damaged"]["blocks"].insert(middle + 1, duplicate)
                request["candidates"][0]["operation"] = "REMOVE_DUPLICATE"
                evidence["trusted_insertions"] = []
                evidence["trusted_identities"] = [{"retained_block_id": missing["block_id"],
                    "duplicate_block_id": "extra-duplicate", "text_sha256": missing["text_sha256"], "source_id": entry["source_id"]}]
                if condition == "wrong-retained":
                    candidate["blocks"][middle] = duplicate
            elif condition == "no-change":
                request["damaged"] = copy.deepcopy(gold)
                request["candidates"] = []
                evidence["trusted_insertions"] = []
            elif condition == "missing-evidence":
                evidence["trusted_insertions"] = []
            elif condition in {"wrong-hash", "forged-evidence"}:
                candidate["blocks"][middle]["text_sha256"] = digest(f"false-content:{source}")
                if condition == "forged-evidence":
                    evidence["trusted_insertions"][0]["text_sha256"] = candidate["blocks"][middle]["text_sha256"]
            elif condition == "wrong-location":
                candidate["blocks"].insert(1, candidate["blocks"].pop(middle))
            elif condition == "wrong-id":
                candidate["blocks"][middle]["block_id"] = "wrong-identity"
            elif condition == "extra-metadata":
                candidate["blocks"][middle]["section_level"] = 1
            elif condition == "unrelated-edit":
                candidate["blocks"][0]["text_sha256"] = digest(f"unrelated-edit:{source}")
            elif condition == "conflicting-evidence":
                evidence["trusted_insertions"].append({**entry, "text_sha256": digest(f"conflict:{source}")})
            elif condition == "supported-ambiguity":
                alternative = copy.deepcopy(request["candidates"][0])
                alternative["candidate_id"] = "candidate-2"
                alternative["document"]["blocks"][middle] = {**missing, "block_id": "alternative-identity", "text_sha256": digest(f"alternative:{source}")}
                request["candidates"].append(alternative)
                evidence["trusted_insertions"].append({**entry, "block_id": "alternative-identity", "text_sha256": digest(f"alternative:{source}")})
            elif condition == "reordered":
                candidate["blocks"][0], candidate["blocks"][1] = candidate["blocks"][1], candidate["blocks"][0]
            cases[name] = request, copy.deepcopy(gold)
    return cases


def emit(root: Path) -> None:
    cases = build_cases()
    for directory in ("stress_challenge", "stress_gold"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name, (request, gold) in cases.items():
        for directory, value in (("stress_challenge", request), ("stress_gold", gold)):
            (root / directory / (name + ".json")).write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    manifest = {"schema_version": "biosure.stress-provenance/1.0", "seed": "biosure-stress-20260930-v1",
                "generator": "scripts/build_stress_challenge.py", "source_graphs": 12, "cases": 168,
                "paragraph_counts": [16, 32, 64], "conditions": list(CONDITIONS),
                "origin": "project-authored fictitious OoC document conversion hashes",
                "limitations": "Exploratory constructed stress test. Same-origin reference/gold. Forged reference is deliberately false; its gold remains unchanged. Not real articles or biological validation."}
    (root / "stress_provenance.json").write_bytes((json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    emit(parser.parse_args().output_dir)
