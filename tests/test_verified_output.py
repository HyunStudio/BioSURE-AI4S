"""Exclusive-write/readback tests with pytest-owned temporary paths."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from biosure.schema import canonical_bytes, loads_json, parse_document
from biosure.gate import Decision
from biosure.verified_output import write_verified_output
from biosure.verified_restore import review_verified_restoration
from test_verified_restore import provider_for, request_for
from test_verified_source import GRAPH, KEY


def selected():
    damaged = parse_document({**GRAPH.to_mapping(), "blocks": [GRAPH.blocks[0].__dict__, GRAPH.blocks[2].__dict__]})
    return review_verified_restoration(request_for(damaged, GRAPH), KEY, provider_for(GRAPH))


def test_exclusive_output_readback_and_receipt(tmp_path):
    result = selected()
    destination = tmp_path / "restored.json"
    written = write_verified_output(result, destination)
    expected = canonical_bytes(GRAPH.to_mapping())
    assert destination.read_bytes() == expected
    assert parse_document(loads_json(destination.read_text(encoding="utf-8"))) == GRAPH
    assert written["status"] == "WRITTEN"
    assert written["receipt"]["source_binding"] == result["source_binding"]
    assert written["receipt"]["output_sha256"] == hashlib.sha256(expected).hexdigest()
    assert written["receipt"]["rule_version"] == "verified-output/1"


def test_existing_destination_is_never_replaced(tmp_path):
    destination = tmp_path / "already.json"
    destination.write_bytes(b"original")
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert destination.read_bytes() == b"original"


def test_abstained_result_cannot_write(tmp_path):
    result = selected()
    result["selected_output"] = None
    destination = tmp_path / "no.json"
    written = write_verified_output(result, destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert not destination.exists()


def test_incomplete_or_inconsistent_selection_never_creates_output(tmp_path):
    def missing_raw(result):
        del result["source_binding"]["raw_sha256"]

    def bad_raw(result):
        result["source_binding"]["raw_sha256"] = "not-a-digest"

    def missing_scope(result):
        result["source_binding"]["scope_id"] = ""

    def wrong_version(result):
        result["receipt"]["rule_version"] = "unknown-selection/9"

    def wrong_candidate(result):
        result["receipt"]["candidate_id"] = "other"

    def wrong_record(result):
        result["source_binding"]["record_id"] = "a-different-record"

    def absent_decision_candidate(result):
        result["decision"] = Decision("AUTO_REPAIR", None, ())

    for index, damage in enumerate((missing_raw, bad_raw, missing_scope, wrong_version,
                                    wrong_candidate, wrong_record, absent_decision_candidate)):
        result = selected()
        damage(result)
        destination = tmp_path / f"invalid-{index}.json"
        written = write_verified_output(result, destination)
        assert written["status"] == "ABSTAIN" and written["receipt"] is None
        assert not destination.exists()


def test_malformed_internal_graph_abstains_without_exception(tmp_path):
    result = selected()
    result["selected_output"] = replace(GRAPH, blocks=(object(),))
    destination = tmp_path / "invalid-graph.json"
    written = write_verified_output(result, destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert not destination.exists()


def test_changed_readback_removes_only_new_output(tmp_path, monkeypatch):
    import biosure.verified_output as output
    monkeypatch.setattr(output, "_readback", lambda path: b"tampered")
    destination = tmp_path / "bad.json"
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert not destination.exists()


def test_interrupted_write_has_no_receipt_or_new_file(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def interrupted(handle, data):
        handle.write(data[:5])
        raise OSError("simulated interruption")

    monkeypatch.setattr(output, "_write_bytes", interrupted)
    destination = tmp_path / "partial.json"
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert not destination.exists()


def test_keyboard_interrupt_cleans_owned_new_file_and_propagates(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def interrupted(handle, data):
        handle.write(data[:5])
        raise KeyboardInterrupt()

    monkeypatch.setattr(output, "_write_bytes", interrupted)
    destination = tmp_path / "keyboard-partial.json"
    with pytest.raises(KeyboardInterrupt):
        write_verified_output(selected(), destination)
    assert not destination.exists()


def test_identity_probe_failure_discloses_unverified_new_path(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def cannot_identify(_fd):
        raise OSError("simulated fstat failure")

    monkeypatch.setattr(output.os, "fstat", cannot_identify)
    destination = tmp_path / "created-but-unidentified.json"
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert written["reason"] == "OUTPUT_CLEANUP_UNVERIFIED"
    assert written["failure_path"] == str(destination)
    assert destination.exists() and destination.read_bytes() == b""


def test_late_file_exists_during_identity_probe_is_not_preexisting(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def late_exists(_fd):
        raise FileExistsError("after exclusive create")

    monkeypatch.setattr(output.os, "fstat", late_exists)
    destination = tmp_path / "created-not-preexisting.json"
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert written["reason"] == "OUTPUT_CLEANUP_UNVERIFIED"
    assert written["failure_path"] == str(destination)
    assert destination.exists() and destination.read_bytes() == b""


def test_identity_probe_interrupt_names_unverified_new_path(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def interrupted_probe(_fd):
        raise KeyboardInterrupt()

    monkeypatch.setattr(output.os, "fstat", interrupted_probe)
    destination = tmp_path / "interrupted-identity.json"
    with pytest.raises(KeyboardInterrupt) as caught:
        write_verified_output(selected(), destination)
    assert destination.exists() and destination.read_bytes() == b""
    assert str(destination) in " ".join(getattr(caught.value, "__notes__", ()))


def test_late_file_exists_error_cleans_owned_new_file(tmp_path, monkeypatch):
    import biosure.verified_output as output

    def late_error(path):
        raise FileExistsError("from readback, after creation")

    monkeypatch.setattr(output, "_readback", late_error)
    destination = tmp_path / "late-exists.json"
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert not destination.exists()


def test_replaced_output_even_with_same_bytes_has_no_receipt(tmp_path, monkeypatch):
    import biosure.verified_output as output
    destination = tmp_path / "swapped.json"
    displaced = tmp_path / "displaced.json"

    def swap(path):
        path.rename(displaced)
        data = displaced.read_bytes()
        path.write_bytes(data)
        return data

    monkeypatch.setattr(output, "_readback", swap)
    written = write_verified_output(selected(), destination)
    assert written["status"] == "ABSTAIN" and written["receipt"] is None
    assert destination.exists() and displaced.exists()


def test_receipt_uses_validated_binding_snapshot(tmp_path, monkeypatch):
    import biosure.verified_output as output
    result = selected()
    original_binding = dict(result["source_binding"])

    def mutate_selection_after_write(path):
        result["source_binding"]["scope_id"] = "changed-after-selection"
        return path.read_bytes()

    monkeypatch.setattr(output, "_readback", mutate_selection_after_write)
    written = write_verified_output(result, tmp_path / "snapshot.json")
    assert written["status"] == "WRITTEN"
    assert written["receipt"]["source_binding"] == original_binding


def test_input_path_remains_byte_identical(tmp_path):
    source = tmp_path / "input.json"
    source.write_bytes(b"do not touch this original input")
    original = source.read_bytes()
    written = write_verified_output(selected(), tmp_path / "new.json")
    assert written["status"] == "WRITTEN"
    assert source.read_bytes() == original
