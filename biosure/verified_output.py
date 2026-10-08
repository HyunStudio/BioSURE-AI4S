"""Internal exclusive output write with canonical byte/graph readback.

This is output integrity, not independent authentication of the source.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .gate import Decision
from .schema import Document, canonical_bytes, loads_json, parse_document, sha256


_BINDING_KEYS = frozenset({"record_id", "version_id", "scope_id", "raw_sha256", "graph_sha256", "extractor_version"})
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _write_bytes(handle, data: bytes) -> None:
    handle.write(data)
    handle.flush()
    os.fsync(handle.fileno())


def _readback(path: Path) -> bytes:
    return path.read_bytes()


def _failure(reason: str, path: Path | None = None) -> dict:
    result = {"status": "ABSTAIN", "receipt": None, "reason": reason}
    if path is not None:
        result["failure_path"] = str(path)
    return result


def write_verified_output(result: dict, destination: Path) -> dict:
    """Create a new file only, and issue a receipt after exact path readback."""
    if not isinstance(result, dict):
        return _failure("INVALID_SELECTION")
    decision = result.get("decision")
    selected = result.get("selected_output")
    binding = result.get("source_binding")
    selection_receipt = result.get("receipt")
    if (not isinstance(decision, Decision) or decision.action != "AUTO_REPAIR"
            or not isinstance(selected, Document) or not isinstance(binding, dict)
            or not isinstance(selection_receipt, dict)):
        return _failure("INVALID_SELECTION")
    try:
        binding_snapshot = dict(binding)
        if (set(binding_snapshot) != _BINDING_KEYS
                or any(not isinstance(binding_snapshot[key], str) or not binding_snapshot[key].strip()
                       for key in _BINDING_KEYS)
                or any(_HEX64.fullmatch(binding_snapshot[key]) is None
                       for key in ("raw_sha256", "graph_sha256"))
                or set(selection_receipt) != {"rule_version", "status", "candidate_id", "source_binding"}
                or selection_receipt["rule_version"] != "verified-source-selection/1"
                or selection_receipt["status"] != "SELECTED_NOT_WRITTEN"
                or not isinstance(decision.candidate_id, str) or not decision.candidate_id.strip()
                or decision.reason_codes != ()
                or selection_receipt["candidate_id"] != decision.candidate_id
                or selection_receipt["source_binding"] != binding_snapshot):
            return _failure("INVALID_SELECTION")
        graph = parse_document(selected.to_mapping())
        if (graph != selected or not graph.blocks
                or graph.record_id != binding_snapshot["record_id"]
                or binding_snapshot["graph_sha256"] != sha256(graph.to_mapping())):
            return _failure("INVALID_GRAPH")
        data = canonical_bytes(graph.to_mapping())
        path = Path(destination)
    except (ValueError, TypeError, OSError):
        return _failure("INVALID_OUTPUT")
    created = False
    created_identity = None
    try:
        with path.open("xb") as handle:
            created = True
            stat = os.fstat(handle.fileno())
            created_identity = (stat.st_dev, stat.st_ino)
            _write_bytes(handle, data)
        actual = _readback(path)
        if actual != data:
            raise ValueError("output bytes differ")
        checked = parse_document(loads_json(actual.decode("utf-8")))
        if checked != graph or sha256(checked.to_mapping()) != binding_snapshot["graph_sha256"]:
            raise ValueError("output graph differs")
        readback_stat = path.stat(follow_symlinks=False)
        if (readback_stat.st_dev, readback_stat.st_ino) != created_identity:
            raise ValueError("output identity changed")
        return {
            "status": "WRITTEN", "path": str(path),
            "receipt": {
                "rule_version": "verified-output/1", "integrity_only": True,
                "source_binding": binding_snapshot,
                "document_sha256": binding_snapshot["graph_sha256"],
                "output_sha256": hashlib.sha256(actual).hexdigest(),
            },
        }
    except BaseException as exc:
        if isinstance(exc, FileExistsError) and not created:
            return _failure("DESTINATION_EXISTS")
        if created and created_identity is None:
            if not isinstance(exc, Exception):
                exc.add_note(f"New output identity could not be verified; inspect without overwriting: {path}")
                raise
            return _failure("OUTPUT_CLEANUP_UNVERIFIED", path)
        if created_identity is not None:
            try:
                stat = path.stat(follow_symlinks=False)
                if (stat.st_dev, stat.st_ino) == created_identity:
                    path.unlink()
                else:
                    if not isinstance(exc, Exception):
                        raise
                    return _failure("OUTPUT_CHANGED_DURING_FAILURE", path)
            except OSError:
                if not isinstance(exc, Exception):
                    raise
                return _failure("OUTPUT_CLEANUP_UNVERIFIED", path)
        if not isinstance(exc, Exception):
            raise
        if isinstance(exc, (OSError, ValueError, TypeError, UnicodeError, KeyError)):
            return _failure(type(exc).__name__)
        raise
