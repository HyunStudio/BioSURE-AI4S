"""Gold-blind learned proposal comparison on the frozen eight-source audit.

This is a document correspondence task over declared JATS references and
observed PDF text layers, not evidence that either source is scientifically
correct. The held-out source IDs and all model settings are fixed in advance.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from .learned_upstream import propose_learned
from .ml_review import pair_features, validate_model
from .prospective_audit import preflight_manifest
from .schema import loads_json, sha256


LOCKED_SOURCES = (
    ("PMC12624441", "development"),
    ("PMC12864593", "development"),
    ("PMC12850162", "development"),
    ("PMC12838518", "development"),
    ("PMC12838946", "held_out"),
    ("PMC12789962", "held_out"),
    ("PMC12755145", "held_out"),
    ("PMC12732092", "held_out"),
)
FOLLOWUP_LOCKED_SOURCES = (
    ("PMC12715219", "held_out"),
    ("PMC12707140", "held_out"),
)


def _locked_sources(manifest: dict, root: Path, model: dict, locked_sources: tuple) -> list[dict]:
    if locked_sources not in (LOCKED_SOURCES, FOLLOWUP_LOCKED_SOURCES):
        raise ValueError("unrecognized source-order lock")
    validate_model(model)
    sources = preflight_manifest(manifest, root)
    if tuple((item["source_id"], item["split"]) for item in sources) != locked_sources:
        raise ValueError("locked source order or split changed")
    experiment = loads_json((root / "results/ml_evaluation.json").read_text(encoding="utf-8"))
    if experiment.get("model") != model:
        raise ValueError("model differs from frozen training evaluation")
    trained = {source_id for group in ("train_sources", "dev_sources", "test_sources")
               for source_id in experiment["split"][group]}
    if trained & {source_id for source_id, _ in locked_sources}:
        raise ValueError("audit source overlaps learned training/evaluation corpus")
    for source in sources:
        if source["license_uri"] != "https://creativecommons.org/licenses/by/4.0/":
            raise ValueError("locked source requires CC BY 4.0")
        if [unit["unit_id"] for unit in source["units"]] != [source["source_id"] + "-title",
                                                        source["source_id"] + "-abstract"]:
            raise ValueError("locked source title/abstract units changed")
    return sources


def _rank(method: str, reference: list[str], observed: list[str]) -> list[int]:
    winners = []
    for text in observed:
        if method == "difflib":
            scores = [difflib.SequenceMatcher(None, candidate.casefold(), text.casefold()).ratio()
                      for candidate in reference]
        elif method == "token_dice":
            scores = [pair_features(candidate, text)[1] for candidate in reference]
        else:
            raise ValueError("unknown lexical comparator")
        winners.append(max(range(len(scores)), key=lambda index: (scores[index], -index)))
    return winners


def decide_upstream_manifest(manifest: dict, root: Path, model: dict, *,
                             locked_sources: tuple = LOCKED_SOURCES) -> list[dict]:
    """Run all alignments and gate checks without opening any gold bytes."""
    root = root.resolve()
    sources = _locked_sources(manifest, root, model, locked_sources)
    decisions = []
    for source in sources:
        complete = all(unit["status"] == "scorable" for unit in source["units"])
        item = {"source_id": source["source_id"], "split": source["split"],
                "units": source["units"], "source": source,
                "eligible": complete, "inputs": None, "proposal": None,
                "difflib_indices": None, "token_dice_indices": None}
        if any(unit["status"] == "scorable" for unit in source["units"]):
            item["inputs"] = loads_json((root / source["inputs_path"]).read_text(encoding="utf-8"))
            declared = item["inputs"].get("source")
            if not isinstance(declared, dict) or any(
                    declared.get(input_key) != source[manifest_key]
                    for input_key, manifest_key in (("id", "source_id"), ("pmcid", "pmcid"),
                                                    ("doi", "doi"), ("license_uri", "license_uri"))):
                raise ValueError("source metadata disagrees with locked manifest")
        if complete:
            inputs = item["inputs"]
            cases = inputs["cases"]
            expected = [source["source_id"] + "-title", source["source_id"] + "-abstract"]
            if [case.get("case_id") for case in cases] != expected:
                raise ValueError("locked source case order changed")
            if any(len(case.get("reference_paragraphs", [])) != 1 or
                   len(case.get("observed_paragraphs", [])) != 1 for case in cases):
                raise ValueError("locked source requires one text unit per title/abstract case")
            reference = [case["reference_paragraphs"][0] for case in cases]
            observed = [case["observed_paragraphs"][0] for case in cases]
            payload = {"record_id": source["source_id"],
                       "reference_paragraphs": reference, "observed_paragraphs": observed}
            item.update({"proposal": propose_learned(payload, model),
                         "difflib_indices": _rank("difflib", reference, observed),
                         "token_dice_indices": _rank("token_dice", reference, observed)})
        decisions.append(item)
    return decisions


def _bucket() -> dict:
    return {"attempted_sources": 0, "eligible_sources": 0, "attempted_units": 0,
            "scorable_units": 0, "compared_units": 0, "discrepancy_units": 0,
            "unscorable": [],
            "learned": {"ranking_correct_units": 0, "proposal_exact_units": 0,
                        "proposal_incorrect_units": 0, "proposal_abstained_units": 0,
                        "gate_auto_repair_sources": 0},
            "difflib": {"ranking_correct_units": 0},
            "token_dice": {"ranking_correct_units": 0},
            "direct_copy": {"exact_units": 0},
            "reversed_reference_failure_control": {"exact_units": 0}}


def _load_gold(source: dict, root: Path, inputs: dict | None) -> list[str] | None:
    if inputs is None:
        return None
    raw = (root / source["gold_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["gold_sha256"]:
        raise ValueError("gold digest mismatch: " + source["source_id"])
    gold = loads_json(raw.decode("utf-8"))
    if gold.get("schema_version") != "biosure.native-pilot-gold/1.0" or gold.get("input_sha256") != sha256(inputs):
        raise ValueError("gold input identity mismatch: " + source["source_id"])
    expected_ids = [case["case_id"] for case in inputs["cases"]]
    if [case.get("case_id") for case in gold.get("cases", [])] != expected_ids:
        raise ValueError("gold case IDs changed: " + source["source_id"])
    gold_texts = []
    for case, answer in zip(inputs["cases"], gold["cases"]):
        paragraphs = answer.get("gold_paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) != 1 or not isinstance(paragraphs[0], str) or not paragraphs[0]:
            raise ValueError("gold unit invalid: " + case["case_id"])
        observed = case["observed_paragraphs"]
        if case.get("condition") not in {"control", "native_extraction_error"}:
            raise ValueError("invalid gold condition: " + case["case_id"])
        if (case["condition"] == "control") != (observed == paragraphs):
            raise ValueError("gold condition mismatch: " + case["case_id"])
        gold_texts.append(paragraphs[0])
    return gold_texts


def evaluate_upstream_manifest(manifest: dict, root: Path, model: dict, *,
                               locked_sources: tuple = LOCKED_SOURCES) -> dict:
    """Score only after every source decision has been computed."""
    root = root.resolve()
    decisions = decide_upstream_manifest(manifest, root, model, locked_sources=locked_sources)
    buckets = {split: _bucket() for split in ("overall", "development", "held_out")}
    source_results = []
    public_decisions = []
    for item in decisions:
        source = item["source"]
        gold = _load_gold(source, root, item["inputs"])
        compact = {"source_id": item["source_id"], "split": item["split"],
                   "input_sha256": source.get("inputs_sha256"),
                   "eligible": item["eligible"]}
        measures = _bucket()
        measures["attempted_sources"] = 1
        measures["attempted_units"] = len(source["units"])
        measures["scorable_units"] = sum(unit["status"] == "scorable" for unit in source["units"])
        measures["unscorable"] = [{"source_id": item["source_id"], "unit_id": unit["unit_id"],
                                   "reason": unit["reason"]} for unit in source["units"]
                                  if unit["status"] == "unscorable"]
        if item["eligible"]:
            cases = item["inputs"]["cases"]
            reference = [case["reference_paragraphs"][0] for case in cases]
            observed = [case["observed_paragraphs"][0] for case in cases]
            proposal = item["proposal"]
            proposed = proposal["proposed_paragraphs"]
            learned_indices = [match["reference_index"] for match in proposal["correspondences"]]
            measures["eligible_sources"] = 1
            measures["compared_units"] = len(gold)
            measures["discrepancy_units"] = sum(left != right for left, right in zip(observed, gold))
            measures["learned"]["ranking_correct_units"] = sum(reference[index] == answer
                                                               for index, answer in zip(learned_indices, gold))
            measures["difflib"]["ranking_correct_units"] = sum(reference[index] == answer
                                                               for index, answer in zip(item["difflib_indices"], gold))
            measures["token_dice"]["ranking_correct_units"] = sum(reference[index] == answer
                                                                  for index, answer in zip(item["token_dice_indices"], gold))
            measures["direct_copy"]["exact_units"] = sum(left == right for left, right in zip(reference, gold))
            measures["reversed_reference_failure_control"]["exact_units"] = sum(
                left == right for left, right in zip(reference[::-1], gold))
            if proposed is None:
                measures["learned"]["proposal_abstained_units"] = len(gold)
            else:
                measures["learned"]["proposal_exact_units"] = sum(left == right for left, right in zip(proposed, gold))
                measures["learned"]["proposal_incorrect_units"] = len(gold) - measures["learned"]["proposal_exact_units"]
                measures["learned"]["gate_auto_repair_sources"] = int(
                    proposal["proposal_check"]["decision"]["action"] == "AUTO_REPAIR")
            compact.update({"learned_indices": learned_indices,
                            "learned_probabilities": [match["probability"] for match in proposal["correspondences"]],
                            "difflib_indices": item["difflib_indices"],
                            "token_dice_indices": item["token_dice_indices"],
                            "proposal_status": proposal["proposal_status"],
                            "proposal_reason": proposal["proposal_reason"],
                            "proposal_sha256": proposal["upstream_receipt"]["proposal_sha256"],
                            "proposal_gate_action": (proposal["proposal_check"]["decision"]["action"]
                                                     if proposal["proposal_check"] else None),
                            "upstream_receipt_sha256": proposal["upstream_receipt"]["receipt_sha256"]})
        else:
            compact.update({"proposal_status": "NOT_EVALUABLE", "proposal_reason": "INCOMPLETE_SOURCE"})
        public_decisions.append(compact)
        source_results.append({"source_id": item["source_id"], "split": item["split"],
                               "metrics": measures, "decision": compact})
        for split in ("overall", item["split"]):
            bucket = buckets[split]
            for key in ("attempted_sources", "eligible_sources", "attempted_units", "scorable_units",
                        "compared_units", "discrepancy_units"):
                bucket[key] += measures[key]
            bucket["unscorable"].extend(measures["unscorable"])
            for method in ("learned", "difflib", "token_dice", "direct_copy", "reversed_reference_failure_control"):
                for metric, value in measures[method].items():
                    bucket[method][metric] += value
    return {"schema_version": "biosure.learned-upstream-audit/1.0",
            "protocol_sha256": manifest["protocol_sha256"],
            "manifest_sha256": sha256(manifest), "model_sha256": sha256(model),
            "decisions_sha256": sha256(public_decisions), "decisions": public_decisions,
            "summary": {**buckets, "sources": source_results},
            "limitations": ["Reference text and JATS gold come from the same article; direct-copy perfection is expected by construction.",
                            ("Eight selected sources and four held-out sources are too few for a superiority or significance claim."
                             if locked_sources == LOCKED_SOURCES else
                             "Two additional selected sources are too few for a superiority or significance claim."),
                            "A fitted correspondence score cannot authenticate reference truth or biological meaning; proposed text is copied from declared references.",
                            "A single development agent checked source boundaries; there is no independent expert or timed human-use study.",
                            "The reversed-reference control is deliberately invalid and is not a deployable comparator."]}
