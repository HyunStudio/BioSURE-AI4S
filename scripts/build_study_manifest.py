"""Freeze a study instrument; this does not produce participant results."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

from biosure.learned_upstream import propose_learned
from biosure.workflow import run_proposal, run_workflow


PUBLIC_INPUTS = (
    ("prospective_ooc_PMC12864593_inputs.json", "PMC12864593-title"),
    ("prospective_ooc_PMC12789962_inputs.json", "PMC12789962-title"),
    ("followup_ooc_PMC12707140_inputs.json", "PMC12707140-title"),
)


def _plain_diff(supplied: dict) -> list[dict]:
    matcher = difflib.SequenceMatcher(
        a=supplied["observed_paragraphs"],
        b=supplied["reference_paragraphs"],
        autojunk=False,
    )
    return [
        {"tag": tag, "observed_span": [i1, i2], "reference_span": [j1, j2]}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def _task(identifier: str, label: str, kind: str, source: dict,
          supplied: dict, model: dict) -> dict:
    learned = propose_learned(supplied, model)
    proposed = learned["proposed_paragraphs"]
    return {
        "id": identifier,
        "label": label,
        "kind": kind,
        "source": source,
        "input": supplied,
        "plain_diff": _plain_diff(supplied),
        "biosure": run_workflow(supplied),
        "learned": learned,
        "learned_gate": run_proposal({**supplied, "proposed_paragraphs": proposed})
        if proposed is not None else None,
    }


def build_study_manifest(root: Path) -> dict:
    fixtures = root / "fixtures"
    model = json.loads((fixtures / "ml_model.json").read_text(encoding="utf-8"))
    examples = json.loads((fixtures / "workflow_examples.json").read_text(encoding="utf-8"))
    tasks = [
        _task(item["record_id"], f"Fictional control {index + 1}", "fictional",
              {"note": "Project-authored fictional control"}, item, model)
        for index, item in enumerate(examples)
    ]
    for filename, case_id in PUBLIC_INPUTS:
        record = json.loads((fixtures / filename).read_text(encoding="utf-8"))
        case = next(item for item in record["cases"] if item["case_id"] == case_id)
        source = record["source"]
        metadata = {key: source[key] for key in (
            "article_url", "authors", "doi", "license_uri", "pdf_sha256", "title", "change_notice"
        )}
        metadata["selection"] = "article page 1 full title only"
        supplied = {
            "record_id": f"study-{case_id}",
            "observed_paragraphs": case["observed_paragraphs"],
            "reference_paragraphs": case["reference_paragraphs"],
        }
        tasks.append(_task(f"public-{case_id}", f"Public title {case_id}",
                           "public-article", metadata, supplied, model))
    task_bytes = json.dumps(tasks, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": "biosure.practical-study/1.0",
        "manifest_sha256": hashlib.sha256(task_bytes).hexdigest(),
        "scope": "instrument-only; no human data or independently adjudicated natural-source truth",
        "generated_from": [
            "fixtures/workflow_examples.json", "fixtures/ml_model.json",
            *[f"fixtures/{filename}" for filename, _ in PUBLIC_INPUTS],
            "biosure.workflow.run_workflow/run_proposal", "biosure.learned_upstream.propose_learned",
            "difflib.SequenceMatcher",
        ],
        "tasks": tasks,
    }


def write_study_manifest(root: Path) -> bytes:
    payload = (json.dumps(build_study_manifest(root), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
    target = root / "docs/study/manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return payload


if __name__ == "__main__":
    write_study_manifest(Path(__file__).resolve().parents[1])
