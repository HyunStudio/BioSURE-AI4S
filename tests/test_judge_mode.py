"""Static judge replay must be an exact, attributed export of engine decisions."""

from pathlib import Path

from biosure.learned_upstream import propose_learned
from biosure.schema import loads_json
from biosure.workflow import run_proposal, run_workflow
from scripts.build_judge_mode import build_judge_data, write_judge_data


ROOT = Path(__file__).resolve().parents[1]


def test_judge_replay_uses_public_and_explicitly_fictional_inputs():
    data = build_judge_data(ROOT)
    assert data["schema_version"] == "biosure.judge-replay/1.0"
    assert [item["id"] for item in data["scenarios"]] == [
        "public-pmc12864593", "fictional-omission", "fictional-invented-proposal"
    ]
    public = data["scenarios"][0]
    assert public["kind"] == "public-excerpt"
    assert public["source"]["article_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC12864593/"
    assert public["source"]["license_uri"] == "https://creativecommons.org/licenses/by/4.0/"
    assert len(public["input"]["reference_paragraphs"]) == 1
    assert public["source"]["selection"] == "article page 1 full title only; abstract excluded from Judge Mode"
    assert all(item["kind"] == "fictional" for item in data["scenarios"][1:])
    assert "gold" not in str(data).lower()
    assert "pdf_bytes" not in str(data).lower()


def test_judge_replay_decisions_are_exact_engine_outputs():
    model = loads_json((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    for scenario in build_judge_data(ROOT)["scenarios"]:
        supplied = scenario["input"]
        assert scenario["workflow"] == run_workflow(supplied)
        assert scenario["learned"] == propose_learned(supplied, model)
        assert scenario["proposal"] == run_proposal({
            **supplied, "proposed_paragraphs": scenario["proposed_paragraphs"]
        })
        assert scenario["workflow"]["receipt"]["receipt_sha256"]
    public = build_judge_data(ROOT)["scenarios"][0]
    assert public["workflow"]["decision"]["action"] == "ABSTAIN"
    assert public["workflow"]["selected_paragraphs"] is None
    assert build_judge_data(ROOT)["scenarios"][1]["workflow"]["decision"]["action"] == "AUTO_REPAIR"
    assert build_judge_data(ROOT)["scenarios"][2]["proposal"]["decision"]["action"] == "ABSTAIN"


def test_judge_export_is_byte_identical_to_checked_in_asset():
    expected = (ROOT / "docs/judge/data.json").read_bytes()
    assert write_judge_data(ROOT) == expected
