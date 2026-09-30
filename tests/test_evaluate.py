from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from biosure.baselines import identity_baseline, schema_locality_baseline
from biosure.evaluate import decide_case, score_case, summarize
from biosure.gate import decide
from biosure.schema import parse_request
from test_gate import duplicate, h, insertion


def write_case(tmp_path: Path, payload: dict, gold: dict) -> tuple[Path, Path]:
    request_path = tmp_path / "request.json"
    gold_path = tmp_path / "gold.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    return request_path, gold_path


def test_decision_digest_unchanged_by_gold_permutation(tmp_path: Path) -> None:
    payload = insertion()
    expected_gold = payload["candidates"][0]["document"]
    request_path, gold_path = write_case(tmp_path, payload, expected_gold)
    first = decide_case(request_path)
    gold_path.write_text(json.dumps(payload["damaged"]), encoding="utf-8")
    second = decide_case(request_path)
    gold_path.unlink()
    third = decide_case(request_path)
    assert first.receipt == second.receipt == third.receipt
    assert first.decision.action == "AUTO_REPAIR"


def test_wrong_executable_candidates_counted(tmp_path: Path) -> None:
    good = insertion()
    gold = good["candidates"][0]["document"]
    bad = copy.deepcopy(good)
    bad["candidates"][0]["document"]["blocks"][1]["text_sha256"] = h("wrong")
    request_path, gold_path = write_case(tmp_path, bad, gold)
    result = score_case(decide_case(request_path), gold_path)
    assert result.action == "ABSTAIN"
    assert result.wrong_executable_candidates_total == 1
    assert result.wrong_executable_candidates_accepted == 0
    assert schema_locality_baseline(parse_request(bad)).action == "AUTO_REPAIR"
    assert identity_baseline(parse_request(bad)).action == "ABSTAIN"


def test_abstentions_stay_in_denominator(tmp_path: Path) -> None:
    good = insertion()
    gold = good["candidates"][0]["document"]
    request_path, gold_path = write_case(tmp_path, good, gold)
    accepted = score_case(decide_case(request_path), gold_path)
    missing = copy.deepcopy(good)
    missing["case_id"] = "missing-evidence"
    missing["evidence"]["trusted_insertions"] = []
    request_path.write_text(json.dumps(missing), encoding="utf-8")
    abstained = score_case(decide_case(request_path), gold_path)
    summary = summarize([accepted, abstained])
    assert summary["cases"] == 2
    assert summary["automatic"] == 1
    assert summary["coverage"] == 0.5
    assert summary["abstentions"] == 1


def test_reports_unique_source_graphs_not_independent_variants(tmp_path: Path) -> None:
    good = insertion()
    gold = good["candidates"][0]["document"]
    request_path, gold_path = write_case(tmp_path, good, gold)
    first = score_case(decide_case(request_path), gold_path)
    variant = copy.deepcopy(good)
    variant["case_id"] = "variant"
    variant["evidence"]["trusted_insertions"] = []
    request_path.write_text(json.dumps(variant), encoding="utf-8")
    second = score_case(decide_case(request_path), gold_path)
    summary = summarize([first, second])
    assert summary["source_graphs"] == 1
    assert summary["cases"] == 2


def test_duplicate_operation_scored_exactly(tmp_path: Path) -> None:
    payload = duplicate()
    gold = payload["candidates"][0]["document"]
    request_path, gold_path = write_case(tmp_path, payload, gold)
    result = score_case(decide_case(request_path), gold_path)
    assert result.operation == "REMOVE_DUPLICATE"
    assert result.exact_auto
    assert not result.incorrect_auto


def test_public_fixture_bundle_counts() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    case_paths = sorted((root / "challenge").glob("*.json"))
    assert len(case_paths) == 8
    results = [score_case(decide_case(path), root / "gold" / path.name) for path in case_paths]
    summary = summarize(results)
    assert summary["source_graphs"] == 2
    assert summary["cases"] == 8
    assert summary["automatic"] == 2
    assert summary["exact_auto"] == 2
    assert summary["incorrect_auto"] == 0
    assert summary["abstentions"] == 6
    assert summary["wrong_executable_candidates_total"] == 5
    assert summary["schema_locality_baseline"]["automatic"] == 7
    assert summary["schema_locality_baseline"]["incorrect_auto"] == 4
    assert summary["identity_baseline"]["automatic"] == 0


def test_public_ambiguity_has_distinct_individually_supported_repairs() -> None:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    payload = json.loads((root / "challenge" / "06-insertion-ambiguous.json").read_text(encoding="utf-8"))
    gold = json.loads((root / "gold" / "06-insertion-ambiguous.json").read_text(encoding="utf-8"))
    first, second = payload["candidates"]
    assert first["document"] != second["document"]
    assert first["document"] == gold
    assert second["document"] != gold
    for candidate in (first, second):
        single = dict(payload, candidates=[candidate])
        assert decide(parse_request(single)).action == "AUTO_REPAIR"
    assert decide(parse_request(payload)).reason_codes == ("AMBIGUOUS_CANDIDATES",)


def test_regeneration_matches_checked_in_fixtures(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts" / "build_challenge.py"), str(tmp_path)], check=True)
    paths = [root / "fixtures" / "provenance.json"]
    paths += list((root / "fixtures" / "challenge").glob("*.json"))
    paths += list((root / "fixtures" / "gold").glob("*.json"))
    for path in paths:
        generated = (tmp_path / path.relative_to(root / "fixtures")).read_bytes()
        assert b"\r\n" not in generated
        assert generated == path.read_bytes()
