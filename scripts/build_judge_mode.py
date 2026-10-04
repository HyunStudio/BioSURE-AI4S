"""Export a deterministic, sample-only static replay of the real BioSURE engine."""

from __future__ import annotations

import json
from pathlib import Path

from biosure.learned_upstream import propose_learned
from biosure.schema import loads_json
from biosure.workflow import run_proposal, run_workflow


def _scenario(identifier: str, kind: str, label: str, source: dict,
              supplied: dict, proposed: list[str], model: dict) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "label": label,
        "source": source,
        "input": supplied,
        "proposed_paragraphs": proposed,
        "workflow": run_workflow(supplied),
        "learned": propose_learned(supplied, model),
        "proposal": run_proposal({**supplied, "proposed_paragraphs": proposed}),
    }


def build_judge_data(root: Path) -> dict:
    fixtures = root / "fixtures"
    model = loads_json((fixtures / "ml_model.json").read_text(encoding="utf-8"))
    article = loads_json((fixtures / "prospective_ooc_PMC12864593_inputs.json").read_text(encoding="utf-8"))
    title_case = next(case for case in article["cases"] if case["case_id"] == "PMC12864593-title")
    public_input = {
        "record_id": "judge-public-pmc12864593-title",
        "reference_paragraphs": title_case["reference_paragraphs"],
        "observed_paragraphs": title_case["observed_paragraphs"],
    }
    source = article["source"]
    public_source = {key: source[key] for key in (
        "article_url", "doi", "license_uri", "pdf_sha256", "title", "change_notice"
    )}
    public_source["selection"] = "article page 1 full title only; abstract excluded from Judge Mode"
    examples = loads_json((fixtures / "workflow_examples.json").read_text(encoding="utf-8"))
    omission = next(item for item in examples if item["record_id"] == "sample-omission")
    invented = list(omission["reference_paragraphs"])
    invented[1] = "Invented result not present in the declared reference."
    return {
        "schema_version": "biosure.judge-replay/1.0",
        "generated_from": [
            "fixtures/prospective_ooc_PMC12864593_inputs.json",
            "fixtures/workflow_examples.json",
            "fixtures/ml_model.json",
            "biosure.workflow.run_workflow/run_proposal",
            "biosure.learned_upstream.propose_learned",
        ],
        "scenarios": [
            _scenario("public-pmc12864593", "public-excerpt",
                      "Real CC BY article · complete title", public_source,
                      public_input, public_input["reference_paragraphs"], model),
            _scenario("fictional-omission", "fictional",
                      "Fictional · one internal omission", {"note": "Project-authored fictional text"},
                      omission, omission["reference_paragraphs"], model),
            _scenario("fictional-invented-proposal", "fictional",
                      "Fictional · invented upstream wording", {"note": "Project-authored fictional text"},
                      omission, invented, model),
        ],
    }


def write_judge_data(root: Path) -> bytes:
    payload = (json.dumps(build_judge_data(root), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
    target = root / "docs/judge/data.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return payload


if __name__ == "__main__":
    write_judge_data(Path(__file__).resolve().parents[1])
