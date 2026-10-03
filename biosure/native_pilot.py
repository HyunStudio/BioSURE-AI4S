"""Gold-separated one-source pilot on real PDF text-layer errors.

These policies see the same declared-reference records. Nothing here
authenticates the reference or estimates natural-error prevalence.
"""

from __future__ import annotations

import hashlib
import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .ml_review import review_paragraphs
from .pdf_extract import _normalise_lines
from .schema import sha256
from .workflow import run_workflow


def decide_inputs(inputs: dict, model: dict) -> dict:
    if not isinstance(inputs, dict) or set(inputs) != {"schema_version", "source", "cases"}:
        raise ValueError("pilot inputs require schema_version, source and cases only")
    if inputs["schema_version"] != "biosure.native-pilot-inputs/1.0":
        raise ValueError("unsupported pilot input schema")
    source = inputs["source"]
    if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]:
        raise ValueError("pilot source ID is required")
    if not isinstance(inputs["cases"], list) or not inputs["cases"]:
        raise ValueError("pilot cases are required")
    results = []
    seen = set()
    for item in inputs["cases"]:
        required = {"case_id", "source_locator", "condition", "reference_paragraphs", "observed_paragraphs"}
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("invalid pilot case fields")
        case_id = item["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("duplicate or invalid pilot case ID")
        if item["condition"] not in {"control", "native_extraction_error"}:
            raise ValueError("invalid pilot condition")
        seen.add(case_id)
        payload = {"record_id": case_id, "reference_paragraphs": item["reference_paragraphs"],
                   "observed_paragraphs": item["observed_paragraphs"]}
        workflow = run_workflow(payload)
        learned = review_paragraphs(payload, model)
        changed = bool(workflow["review_changes"])
        results.append({"case_id": case_id, "condition": item["condition"],
                        "observed_paragraphs": workflow["observed_paragraphs"],
                        "biosure": {"action": workflow["decision"]["action"],
                                    "selected_paragraphs": workflow["selected_paragraphs"],
                                    "reason_codes": workflow["decision"]["reason_codes"],
                                    "adapter_status": workflow["adapter_status"]},
                        "direct_copy": {"action": "AUTO_REPLACE",
                                        "output_paragraphs": workflow["reference_paragraphs"]},
                        "diff_review": {"action": "REVIEW" if changed else "NO_CHANGE",
                                        "changed_spans": workflow["review_changes"]},
                        "learned_review": {"correspondences": learned["correspondences"],
                                           "selected_paragraphs": None}})
    output = {"schema_version": "biosure.native-pilot-decisions/1.1",
              "source_id": source["id"], "input_sha256": sha256(inputs), "cases": results,
              "scope": "Selected one-source native PDF extraction pilot; declared reference is unauthenticated."}
    return {**output, "decision_sha256": sha256(output)}


def score_decisions(decisions: dict, gold: dict) -> dict:
    if not isinstance(decisions, dict) or decisions.get("schema_version") != "biosure.native-pilot-decisions/1.1":
        raise ValueError("invalid pilot decisions")
    if not isinstance(gold, dict) or gold.get("schema_version") != "biosure.native-pilot-gold/1.0":
        raise ValueError("invalid pilot gold")
    if decisions.get("decision_sha256") != sha256({key: value for key, value in decisions.items()
                                                   if key != "decision_sha256"}):
        raise ValueError("pilot decision digest mismatch")
    if decisions.get("input_sha256") != gold.get("input_sha256"):
        raise ValueError("pilot input digest mismatch")
    cases, answers = decisions.get("cases"), gold.get("cases")
    if not isinstance(cases, list) or not isinstance(answers, list) or [x.get("case_id") for x in cases] != [x.get("case_id") for x in answers]:
        raise ValueError("pilot case IDs mismatch")
    out = {"schema_version": "biosure.native-pilot-results/1.1", "input_sha256": decisions["input_sha256"],
           "sources": 1, "cases": len(cases),
           "native_error_cases": sum(x["condition"] == "native_extraction_error" for x in cases),
           "biosure": {"exact_auto": 0, "incorrect_auto": 0, "abstentions": 0, "manual_review_records": 0},
           "direct_copy": {"exact_auto": 0, "incorrect_auto": 0, "abstentions": 0},
           "diff_review": {"manual_review_records": 0},
           "learned_review": {"native_error_cases_with_lexical_alerts": 0,
                              "native_error_cases_below_match_threshold": 0,
                              "automatic_repairs": 0}, "case_results": []}
    for item, answer in zip(cases, answers):
        expected = answer.get("gold_paragraphs")
        if not isinstance(expected, list) or not expected or any(not isinstance(text, str) or not text for text in expected):
            raise ValueError("invalid pilot gold paragraphs")
        if item.get("condition") not in {"control", "native_extraction_error"}:
            raise ValueError("invalid pilot condition")
        if (item["condition"] == "control") != (item["observed_paragraphs"] == expected):
            raise ValueError("pilot condition disagrees with observed and gold paragraphs: " + item["case_id"])
        bio = item["biosure"]
        if bio["action"] == "AUTO_REPAIR":
            key = "exact_auto" if bio["selected_paragraphs"] == expected else "incorrect_auto"
            out["biosure"][key] += 1
        else:
            out["biosure"]["abstentions"] += 1
            if item["condition"] != "control":
                out["biosure"]["manual_review_records"] += 1
        copy = item["direct_copy"]
        copy_key = "exact_auto" if copy["output_paragraphs"] == expected else "incorrect_auto"
        out["direct_copy"][copy_key] += 1
        if item["diff_review"]["action"] == "REVIEW":
            out["diff_review"]["manual_review_records"] += 1
        learned = item["learned_review"]
        if learned["selected_paragraphs"] is not None:
            out["learned_review"]["automatic_repairs"] += 1
        if item["condition"] == "native_extraction_error":
            if any(match["flags"] for match in learned["correspondences"]):
                out["learned_review"]["native_error_cases_with_lexical_alerts"] += 1
            if any(not match["above_threshold"] for match in learned["correspondences"]):
                out["learned_review"]["native_error_cases_below_match_threshold"] += 1
        out["case_results"].append({"case_id": item["case_id"], "condition": item["condition"],
                                    "biosure_action": bio["action"], "direct_copy_exact": copy_key == "exact_auto",
                                    "diff_changed_spans": len(item["diff_review"]["changed_spans"])})
    return out


def verify_native_pdf_source(pdf_bytes: bytes, inputs: dict) -> dict:
    """Confirm frozen observed text comes from the stated PDF text layer.

    This checks source identity and pypdf observations, never visual gold.
    The public full PDF has a repository cover before article page one.
    """
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("a PDF byte stream is required")
    source = inputs.get("source") if isinstance(inputs, dict) else None
    if not isinstance(source, dict):
        raise ValueError("pilot source metadata is required")
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    if digest == source.get("full_pdf_sha256"):
        source_format, article_index = "full_pdf_with_cover", 1
    elif digest == source.get("pdf_excerpt_sha256"):
        source_format, article_index = "two_page_excerpt", 0
    else:
        raise ValueError("source PDF SHA-256 does not match frozen source")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted or len(reader.pages) <= article_index:
            raise ValueError("source PDF article page is unavailable")
        page_text, _ = _normalise_lines(reader.pages[article_index].extract_text(extraction_mode="plain") or "")
    except (PdfReadError, KeyError, TypeError, RecursionError) as error:
        raise ValueError("source PDF text layer could not be read") from error
    cases = inputs.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("pilot cases are required")
    for case in cases:
        observed = case.get("observed_paragraphs") if isinstance(case, dict) else None
        if not isinstance(observed, list) or len(observed) != 1 or not isinstance(observed[0], str) or not observed[0]:
            raise ValueError("source verification requires one nonempty observed text unit per case")
        if observed[0] not in page_text:
            raise ValueError("observed text not found on source article page: " + str(case.get("case_id")))
    return {"source_format": source_format, "source_sha256": digest,
            "article_page": article_index + 1, "observed_cases_verified": len(cases), "gold_verified": False}
