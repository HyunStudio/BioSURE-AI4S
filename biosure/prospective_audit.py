"""Locked, source-level PDF text-layer audit."""

import hashlib
import re
from pathlib import Path

from .native_pilot import decide_inputs, score_decisions
from .schema import loads_json


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_BASE_FIELDS = {"source_id", "split", "doi", "pmcid", "license_uri", "units"}
_FILE_FIELDS = {"inputs_path", "inputs_sha256", "gold_path", "gold_sha256"}


def _file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("audit path must be nonempty and relative")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("audit path is outside root or missing: " + relative)
    return path


def _digest_matches(data: bytes, expected: str, label: str) -> None:
    if not isinstance(expected, str) or not _DIGEST.fullmatch(expected):
        raise ValueError(label + " SHA-256 must be lowercase hex")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(label + " digest mismatch")


def preflight_manifest(manifest: dict, root: Path) -> list[dict]:
    """Validate locked inputs and paths without opening any gold bytes."""
    root = root.resolve()
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "protocol_path", "protocol_sha256", "sources"}:
        raise ValueError("invalid prospective audit manifest fields")
    if manifest["schema_version"] != "biosure.prospective-audit/1.0":
        raise ValueError("unsupported prospective audit schema")
    _digest_matches(_file(root, manifest["protocol_path"]).read_bytes(),
                    manifest["protocol_sha256"], "protocol")
    sources = manifest["sources"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("at least one source is required")
    source_ids: set[str] = set()
    unit_ids: set[str] = set()
    case_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("invalid source entry")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            raise ValueError("duplicate or invalid source ID")
        source_ids.add(source_id)
        if source.get("split") not in {"development", "held_out"}:
            raise ValueError("invalid split")
        if any(not isinstance(source.get(key), str) or not source[key].strip()
               for key in ("doi", "pmcid", "license_uri")):
            raise ValueError("source DOI, PMCID and license URI are required")
        units = source.get("units")
        if not isinstance(units, list) or not units:
            raise ValueError("source units are required")
        scorable_ids = []
        for unit in units:
            if not isinstance(unit, dict):
                raise ValueError("invalid unit entry")
            unit_id = unit.get("unit_id")
            if not isinstance(unit_id, str) or not unit_id or unit_id in unit_ids:
                raise ValueError("duplicate or invalid unit ID")
            unit_ids.add(unit_id)
            status = unit.get("status")
            if status == "scorable":
                if set(unit) != {"unit_id", "status", "case_id"}:
                    raise ValueError("scorable unit requires only unit ID, status and case ID")
                case_id = unit["case_id"]
                if not isinstance(case_id, str) or not case_id or case_id in case_ids:
                    raise ValueError("duplicate or invalid case ID")
                case_ids.add(case_id)
                scorable_ids.append(case_id)
            elif status == "unscorable":
                if set(unit) != {"unit_id", "status", "reason"} or not isinstance(unit.get("reason"), str) or not unit["reason"].strip():
                    raise ValueError("unscorable unit requires a reason")
            else:
                raise ValueError("invalid unit status")
        required_fields = _BASE_FIELDS | (_FILE_FIELDS if scorable_ids else set())
        if set(source) != required_fields:
            raise ValueError("source file fields do not match scorable units")
        if scorable_ids:
            inputs_path = _file(root, source["inputs_path"])
            _digest_matches(inputs_path.read_bytes(), source["inputs_sha256"], "input")
            _file(root, source["gold_path"])
            if not isinstance(source["gold_sha256"], str) or not _DIGEST.fullmatch(source["gold_sha256"]):
                raise ValueError("gold SHA-256 must be lowercase hex")
            inputs = loads_json(inputs_path.read_text(encoding="utf-8"))
            if not isinstance(inputs, dict) or not isinstance(inputs.get("source"), dict) or inputs["source"].get("id") != source_id:
                raise ValueError("source ID disagrees with input")
            cases = inputs.get("cases")
            if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
                raise ValueError("invalid input cases")
            observed_ids = [case.get("case_id") for case in cases]
            if len(observed_ids) != len(set(observed_ids)):
                raise ValueError("duplicate case ID in input")
            if observed_ids != scorable_ids:
                raise ValueError("unit case IDs disagree with input cases")
    return sources


def evaluate_manifest(manifest: dict, root: Path, model: dict) -> dict:
    """Decide every scorable source before opening any gold, then aggregate."""
    root = root.resolve()
    sources = preflight_manifest(manifest, root)
    decided = []
    for source in sources:
        if any(unit["status"] == "scorable" for unit in source["units"]):
            inputs = loads_json(_file(root, source["inputs_path"]).read_text(encoding="utf-8"))
            decided.append({"source_id": source["source_id"], "split": source["split"],
                            "decisions": decide_inputs(inputs, model)})
    by_id = {item["source_id"]: item["decisions"] for item in decided}
    buckets = {key: _empty_bucket() for key in ("overall", "development", "held_out")}
    source_results = []
    for source in sources:
        result = None
        if source["source_id"] in by_id:
            gold_path = _file(root, source["gold_path"])
            gold_bytes = gold_path.read_bytes()
            _digest_matches(gold_bytes, source["gold_sha256"], "gold")
            result = score_decisions(by_id[source["source_id"]],
                                     loads_json(gold_bytes.decode("utf-8")))
        source_results.append({"source_id": source["source_id"], "split": source["split"],
                               "result": result})
        for bucket_name in ("overall", source["split"]):
            bucket = buckets[bucket_name]
            bucket["attempted_sources"] += 1
            bucket["attempted_units"] += len(source["units"])
            for unit in source["units"]:
                if unit["status"] == "unscorable":
                    bucket["unscorable"].append({"source_id": source["source_id"],
                                                   "unit_id": unit["unit_id"],
                                                   "reason": unit["reason"]})
            if result is None:
                continue
            bucket["scorable_sources"] += 1
            bucket["scorable_units"] += result["cases"]
            bucket["native_error_cases"] += result["native_error_cases"]
            for method in ("biosure", "direct_copy", "diff_review", "learned_review"):
                for metric, value in result[method].items():
                    bucket[method][metric] += value
    return {"schema_version": "biosure.prospective-audit-results/1.0",
            "protocol_sha256": manifest["protocol_sha256"],
            "decisions": decided,
            "summary": {**buckets, "source_results": source_results}}


def _empty_bucket() -> dict:
    return {"attempted_sources": 0, "scorable_sources": 0,
            "attempted_units": 0, "scorable_units": 0, "unscorable": [],
            "native_error_cases": 0,
            "biosure": {"exact_auto": 0, "incorrect_auto": 0, "abstentions": 0,
                        "manual_review_records": 0},
            "direct_copy": {"exact_auto": 0, "incorrect_auto": 0, "abstentions": 0},
            "diff_review": {"manual_review_records": 0},
            "learned_review": {"native_error_cases_with_lexical_alerts": 0,
                               "native_error_cases_below_match_threshold": 0,
                               "automatic_repairs": 0}}
