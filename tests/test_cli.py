from __future__ import annotations

import json
import os
import subprocess
import sys
import pytest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, "-m", "biosure.cli", *args],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_blind_evaluate_writes_decisions_before_summary(tmp_path: Path) -> None:
    result = run_cli(
        "blind-evaluate",
        "--cases", str(ROOT / "fixtures" / "challenge"),
        "--gold", str(ROOT / "fixtures" / "gold"),
        "--out", str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "candidate_dependent_public_evaluation"
    assert (summary["cases"], summary["automatic"], summary["exact_auto"]) == (8, 2, 2)
    decisions = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8")
    assert len(decisions.splitlines()) == 8
    assert "gold" not in decisions
    assert "correct" not in decisions


def test_blind_evaluate_refuses_to_replace_existing_output(tmp_path: Path) -> None:
    decisions = tmp_path / 'decisions.jsonl'
    decisions.write_text('existing receipt\n', encoding='utf-8')
    result = run_cli(
        'blind-evaluate', '--cases', str(ROOT / 'fixtures' / 'challenge'),
        '--gold', str(ROOT / 'fixtures' / 'gold'), '--out', str(tmp_path),
    )
    assert result.returncode == 2
    assert decisions.read_text(encoding='utf-8') == 'existing receipt\n'
    assert not (tmp_path / 'summary.json').exists()


def test_legacy_demo_is_visibly_oracle_labeled() -> None:
    result = run_cli("legacy-demo")
    if not (ROOT / "biosure/legacy.py").is_file():
        assert result.returncode == 2
        assert result.stdout == ""
        return
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "known_spec_oracle_diagnostic"
    assert payload["families_tested"] == 6
    assert payload["roundtrips_exact"] == 6
    assert payload["injection_spec_used"] is True
    assert set(payload["family_results"]) == {
        "ADJACENT_PARAGRAPH_SWAP",
        "DUPLICATE_PARAGRAPH_INSERTION",
        "PARAGRAPH_OMISSION_WITH_TRUSTED_JATS_CANDIDATE",
        "SECTION_HEADING_LEVEL_SHIFT",
        "CAPTION_TARGET_MISLINK",
        "CITATION_ANCHOR_DELETION",
    }
    assert all(payload["family_results"].values())


def test_demo_does_not_require_private_import() -> None:
    result = run_cli("demo", "--case", str(ROOT / "fixtures" / "challenge" / "01-insertion-good.json"))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "candidate_dependent_demo"
    assert payload["decision"]["action"] == "AUTO_REPAIR"
    assert "research_selective_structural_recovery_dke" not in result.stdout


def test_missing_case_fails_without_success_artifact(tmp_path: Path) -> None:
    result = run_cli("demo", "--case", str(tmp_path / "missing.json"))
    assert result.returncode != 0
    assert "AUTO_REPAIR" not in result.stdout


def test_prior_aggregate_is_labeled_and_arithmetic_matches() -> None:
    if not (ROOT / "results/dke_prior_aggregate.json").is_file():
        pytest.skip("Prior aggregate intentionally excluded from public profile")
    prior = json.loads((ROOT / "results" / "dke_prior_aggregate.json").read_text(encoding="utf-8"))
    assert prior["evidence_class"] == "unreproduced_article_level_prior"
    assert (prior["held_out"], prior["automatic"], prior["exact_auto"], prior["abstained"]) == (120, 116, 116, 4)
    assert prior["incorrect_accepted"] == 0
    assert abs(prior["nominal_one_sided_95_upper"] - (1 - 0.05 ** (1 / 116))) < 1e-12
