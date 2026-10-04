"""The practical-study instrument must not manufacture participant evidence."""

import difflib
import hashlib
import json
from pathlib import Path

from biosure.learned_upstream import propose_learned
from biosure.workflow import run_proposal, run_workflow
from scripts.build_study_manifest import build_study_manifest, write_study_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_cases_have_rights_and_no_natural_answer_key():
    bundle = build_study_manifest(ROOT)
    assert bundle["schema_version"] == "biosure.practical-study/1.0"
    tasks = bundle["tasks"]
    task_bytes = json.dumps(tasks, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")
    assert bundle["manifest_sha256"] == hashlib.sha256(task_bytes).hexdigest()
    assert len(tasks) == 9
    assert len({task["id"] for task in tasks}) == 9
    assert sum(task["kind"] == "fictional" for task in tasks) == 6
    assert sum(task["kind"] == "public-article" for task in tasks) == 3
    assert "participants" not in bundle and "results" not in bundle
    for task in tasks:
        assert "answer_key" not in task and "correct_disposition" not in task
        assert task["input"]["reference_paragraphs"]
        assert task["input"]["observed_paragraphs"]
        if task["kind"] == "public-article":
            assert task["source"]["article_url"].startswith("https://pmc.ncbi.nlm.nih.gov/articles/")
            assert task["source"]["authors"]
            assert task["source"]["license_uri"] == "https://creativecommons.org/licenses/by/4.0/"
            assert task["source"]["selection"] == "article page 1 full title only"
        else:
            assert task["source"]["note"] == "Project-authored fictional control"


def test_decisions_and_ordinary_diff_replay_independent_paths():
    model = json.loads((ROOT / "fixtures/ml_model.json").read_text(encoding="utf-8"))
    for task in build_study_manifest(ROOT)["tasks"]:
        supplied = task["input"]
        assert task["biosure"] == run_workflow(supplied)
        assert task["learned"] == propose_learned(supplied, model)
        if task["learned"]["proposed_paragraphs"] is None:
            assert task["learned_gate"] is None
        else:
            assert task["learned_gate"] == run_proposal({
                **supplied, "proposed_paragraphs": task["learned"]["proposed_paragraphs"]
            })
        expected = [
            {"tag": tag, "observed_span": [i1, i2], "reference_span": [j1, j2]}
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                a=supplied["observed_paragraphs"],
                b=supplied["reference_paragraphs"], autojunk=False
            ).get_opcodes()
            if tag != "equal"
        ]
        assert task["plain_diff"] == expected


def test_study_manifest_rebuild_is_byte_identical():
    expected = (ROOT / "docs/study/manifest.json").read_bytes()
    actual = write_study_manifest(ROOT)
    assert actual == expected
    assert b"participant" not in actual.lower()
