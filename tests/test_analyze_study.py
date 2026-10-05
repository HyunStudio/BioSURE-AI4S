"""Strict offline analysis of future study exports; these tests create no people."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "study" / "manifest.json"
MODES = (
    ("manual", "diff", "biosure") * 3,
    ("diff", "biosure", "manual") * 3,
    ("biosure", "manual", "diff") * 3,
    ("manual", "diff", "biosure") * 3,
    ("diff", "biosure", "manual") * 3,
    ("biosure", "manual", "diff") * 3,
)


def analyzer():
    return importlib.import_module("scripts.analyze_study")


def frozen_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def session(slot=0):
    bundle = frozen_manifest()
    modes = MODES[slot]
    return {
        "schema_version": "biosure.practical-study-session/1.0",
        "study_scope": "instrument-only; automated or human origin must be reported separately",
        "manifest_sha256": bundle["manifest_sha256"],
        "assignment_slot": slot,
        "records": [
            {
                "task_id": task["id"],
                "source_kind": task["kind"],
                "mode": mode,
                "difference": "unsure",
                "first_changed_reference_position": None,
                "disposition": "escalate",
                "active_ms": 1000 + index,
                "wall_ms": 1200 + index,
            }
            for index, (task, mode) in enumerate(zip(bundle["tasks"], modes))
        ],
    }


def test_manifest_digest_is_recomputed_and_frozen(tmp_path):
    module = analyzer()
    assert module.load_manifest(MANIFEST)["manifest_sha256"] == (
        "dc5d335ec5a6e1b4295cd69d8a7337cfc6a54ada33a2d88442d88038d63f71a0"
    )
    changed = frozen_manifest()
    changed["tasks"][0]["label"] = "Tampered label"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        module.load_manifest(path)


def test_session_accepts_complete_slot_and_rejects_wrong_pairing():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    assert module.validate_session(session(0), bundle)["assignment_slot"] == 0
    assert module.validate_session(session(1), bundle)["assignment_slot"] == 1
    wrong = session(1)
    wrong["records"][0]["mode"] = "manual"
    with pytest.raises(ValueError, match="mode"):
        module.validate_session(wrong, bundle)


@pytest.mark.parametrize("mutation", [
    lambda item: item.update({"private_contact": "not-shared"}),
    lambda item: item.update({"manifest_sha256": "0" * 64}),
    lambda item: item["records"].pop(),
    lambda item: item["records"].append(copy.deepcopy(item["records"][0])),
    lambda item: item["records"][0].update({"active_ms": True}),
    lambda item: item["records"][0].update({"wall_ms": 2}),
    lambda item: item["records"][0].update({"first_changed_reference_position": 0}),
    lambda item: item["records"][0].update({"participant_name": "Alice"}),
])
def test_session_rejects_incomplete_invalid_or_identifiable_data(mutation):
    module = analyzer()
    item = session()
    mutation(item)
    with pytest.raises(ValueError):
        module.validate_session(item, module.load_manifest(MANIFEST))


def test_position_is_required_only_for_yes_and_within_reference():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    good = session()
    good["records"][0].update(difference="yes", first_changed_reference_position=1)
    assert module.validate_session(good, bundle)["records"][0]["first_changed_reference_position"] == 1
    for position in (None, -1, 5, True):
        bad = copy.deepcopy(good)
        bad["records"][0]["first_changed_reference_position"] = position
        with pytest.raises(ValueError, match="position"):
            module.validate_session(bad, bundle)


def test_unhashable_answer_values_are_rejected_as_invalid_input():
    module = analyzer()
    item = session()
    item["records"][0]["difference"] = ["yes"]
    with pytest.raises(ValueError, match="answer"):
        module.validate_session(item, module.load_manifest(MANIFEST))


def test_fingerprint_ignores_record_order_but_not_answers():
    module = analyzer()
    first = session()
    reordered = copy.deepcopy(first)
    reordered["records"].reverse()
    assert module.session_fingerprint(first) == module.session_fingerprint(reordered)
    reordered["records"][0]["difference"] = "no"
    assert module.session_fingerprint(first) != module.session_fingerprint(reordered)


def test_key_requires_frozen_digest_known_tasks_and_exact_fields(tmp_path):
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    key = {
        "schema_version": "biosure.practical-study-key/1.0",
        "manifest_sha256": bundle["manifest_sha256"],
        "answers": {
            "sample-omission": {
                "difference": "yes",
                "first_changed_reference_position": 1,
                "basis": "fictional-author-key",
            },
        },
    }
    path = tmp_path / "key.json"
    path.write_text(json.dumps(key), encoding="utf-8")
    assert module.load_key(path, bundle)["answers"]["sample-omission"]["difference"] == "yes"
    key["answers"]["unknown-task"] = key["answers"].pop("sample-omission")
    path.write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(ValueError, match="key"):
        module.load_key(path, bundle)


def test_key_rejects_unhashable_basis_as_invalid_input(tmp_path):
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    path = tmp_path / "key.json"
    path.write_text(json.dumps({
        "schema_version": "biosure.practical-study-key/1.0",
        "manifest_sha256": bundle["manifest_sha256"],
        "answers": {"sample-omission": {"difference": "yes", "basis": ["independent-adjudication"]}},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="key"):
        module.load_key(path, bundle)


def test_summary_reports_slot_coverage_and_descriptive_time_only():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    result = module.summarize_sessions(bundle, [session(0)])
    assert result["schema_version"] == "biosure.practical-study-analysis/1.0"
    assert result["session_count"] == 1
    assert result["slot_coverage"] == {"present": [0], "missing": [1, 2, 3, 4, 5]}
    assert result["withdrawals_owner_reported"] is None
    assert result["modes"]["manual"]["records"] == 3
    assert result["modes"]["manual"]["active_ms"] == {"median": 1003, "min": 1000, "max": 1006}
    assert result["modes"]["manual"]["difference_counts"]["unsure"] == 3
    assert result["modes"]["manual"]["difference_scored"] == 0
    assert result["cases"]["sample-omission"]["records"] == 1
    assert "p_value" not in result and "speedup" not in result
    assert any("six" in warning for warning in result["warnings"])
    assert any("descriptive" in warning for warning in result["warnings"])


def test_three_consecutive_slots_balance_each_case_once_but_remain_exploratory():
    module = analyzer()
    result = module.summarize_sessions(module.load_manifest(MANIFEST), [session(i) for i in range(3)])
    assert result["session_count"] == 3
    assert result["slot_coverage"] == {"present": [0, 1, 2], "missing": [3, 4, 5]}
    assert all(result["modes"][mode]["records"] == 9 for mode in ("manual", "diff", "biosure"))
    assert all(item["records"] == 3 for item in result["cases"].values())
    assert result["warnings"]


def test_six_distinct_slots_have_no_coverage_warning():
    module = analyzer()
    result = module.summarize_sessions(module.load_manifest(MANIFEST), [session(i) for i in range(6)])
    assert result["session_count"] == 6
    assert result["slot_coverage"] == {"present": [0, 1, 2, 3, 4, 5], "missing": []}
    assert result["warnings"] == []
    assert result["modes"]["manual"]["records"] == 18


def test_summary_rejects_duplicate_content_even_if_record_order_changes():
    module = analyzer()
    second = session()
    second["records"].reverse()
    with pytest.raises(ValueError, match="duplicate"):
        module.summarize_sessions(module.load_manifest(MANIFEST), [session(), second])


def test_keyed_accuracy_never_uses_source_derived_natural_labels():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    item = session()
    item["records"][0].update(difference="yes", first_changed_reference_position=1)
    natural_id = "public-PMC12864593-title"
    natural_record = next(record for record in item["records"] if record["task_id"] == natural_id)
    natural_record["difference"] = "no"
    key = {
        "schema_version": "biosure.practical-study-key/1.0",
        "manifest_sha256": bundle["manifest_sha256"],
        "answers": {
            "sample-omission": {"difference": "yes", "first_changed_reference_position": 1,
                                "basis": "fictional-author-key"},
            natural_id: {"difference": "no", "basis": "source-derived"},
        },
    }
    first = module.summarize_sessions(bundle, [item], key)
    assert first["modes"]["manual"]["difference_scored"] == 1
    assert first["modes"]["manual"]["difference_exact"] == 1
    assert first["modes"]["manual"]["position_scored"] == 1
    assert first["modes"]["manual"]["position_exact"] == 1
    assert sum(mode["difference_scored"] for mode in first["modes"].values()) == 1
    key["answers"][natural_id]["basis"] = "independent-adjudication"
    second = module.summarize_sessions(bundle, [item], key)
    assert sum(mode["difference_scored"] for mode in second["modes"].values()) == 2


def test_summary_rejects_unvalidated_key_claim():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    key = {"schema_version": "biosure.practical-study-key/1.0",
           "manifest_sha256": "0" * 64, "answers": {}}
    with pytest.raises(ValueError, match="key"):
        module.summarize_sessions(bundle, [session()], key)


def test_withdrawals_are_unknown_until_owner_supplies_a_count():
    module = analyzer()
    bundle = module.load_manifest(MANIFEST)
    assert module.summarize_sessions(bundle, [session()])["withdrawals_owner_reported"] is None
    assert module.summarize_sessions(bundle, [session()], withdrawals=2)["withdrawals_owner_reported"] == 2
    with pytest.raises(ValueError, match="withdrawal"):
        module.summarize_sessions(bundle, [session()], withdrawals=True)


def test_cli_prints_deterministic_summary_without_input_filename_or_identifiers(tmp_path, capsys):
    module = analyzer()
    source = tmp_path / "locally-held-session.json"
    source.write_text(json.dumps(session()), encoding="utf-8")
    args = ["--manifest", str(MANIFEST), "--sessions", str(source)]
    assert module.main(args) == 0
    first = capsys.readouterr().out
    assert module.main(args) == 0
    second = capsys.readouterr().out
    assert first == second
    assert "locally-held-session" not in first
    assert "private_contact" not in first
    assert json.loads(first)["session_count"] == 1


def test_cli_refuses_to_overwrite_summary(tmp_path, capsys):
    module = analyzer()
    source = tmp_path / "session.json"
    source.write_text(json.dumps(session()), encoding="utf-8")
    destination = tmp_path / "summary.json"
    destination.write_text("keep", encoding="utf-8")
    result = module.main(["--manifest", str(MANIFEST), "--sessions", str(source), "--out", str(destination)])
    assert result == 2
    assert destination.read_text(encoding="utf-8") == "keep"
    assert "already exists" in capsys.readouterr().err
