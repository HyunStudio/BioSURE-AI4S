"""Locked, source-level PDF text-layer audit."""

import hashlib
import re
from pathlib import Path

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
