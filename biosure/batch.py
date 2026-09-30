"""Local all-or-nothing paragraph triage; never writes original documents."""
from __future__ import annotations

from .workflow import run_workflow


def run_batch(payload: object) -> dict:
    if not isinstance(payload, list) or not 1 <= len(payload) <= 100:
        raise ValueError("batch requires 1 to 100 workflow records")
    results = []
    seen = set()
    for item in payload:
        result = run_workflow(item)
        record_id = result["request"]["damaged"]["record_id"].strip()
        if record_id in seen:
            raise ValueError("duplicate record_id in batch")
        seen.add(record_id)
        results.append(result)
    automatic = sum(r["decision"]["action"] == "AUTO_REPAIR" for r in results)
    unchanged = sum(r["adapter_status"] == "NO_CHANGE" for r in results)
    return {"schema_version": "biosure.batch/1.0",
            "summary": {"records": len(results), "automatic": automatic, "unchanged": unchanged,
                        "review_required": len(results) - automatic - unchanged},
            "results": results}
